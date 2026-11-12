# backend/scaling/deployment_state.py
"""
Manage deployment phase, per-service rollout lifecycle, cooldown timers,
CI/CD webhook ingestion, and durable state persistence for the DPBPS framework.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import DeploymentPhase, ScalingConfig, DecisionAction
import backend.config as cfg

logger = logging.getLogger(__name__)

# Default persistence file path
DEFAULT_PERSISTENCE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "deployment_state.json",
)


class DeploymentStateManager:
    """
    Keeps track of global and per-service deployment phases, cooldown timestamps,
    CI/CD deployment lifecycle events, and Kubernetes rollout state.

    Supports:
    - Per-service deployment phase tracking with fallback to cluster-wide phase.
    - Secure CI/CD webhook event ingestion with HMAC SHA-256 signature verification.
    - Event deduplication and out-of-order rejection.
    - Kubernetes rollout status reconciliation.
    - Atomic JSON disk persistence across FastAPI backend restarts.
    """

    def __init__(
        self,
        persistence_file: Optional[str] = None,
        auto_load: bool = False,
        webhook_secret: Optional[str] = None,
    ) -> None:
        self.persistence_file = persistence_file or getattr(
            cfg, "DEPLOYMENT_STATE_FILE", DEFAULT_PERSISTENCE_FILE
        )
        self.webhook_secret = webhook_secret or getattr(
            cfg, "CICD_WEBHOOK_SECRET", "dpbps-cicd-secret-token"
        )
        self._lock = threading.RLock()

        # Global cluster-wide fallback phase
        self.phase: DeploymentPhase = DeploymentPhase.NORMAL_OPERATION

        # Per-service deployment phases: service_name -> DeploymentPhase
        self.service_phases: Dict[str, DeploymentPhase] = {}

        # Per-service deployment start timestamps (UTC)
        self.deployment_start_times: Dict[str, datetime] = {}

        # service_name -> last scaling action timestamp (UTC)
        self.last_action_time: Dict[str, datetime] = {}

        # service_name -> last action type (DecisionAction value string)
        self.last_action_type: Dict[str, str] = {}

        # service_name -> timestamp when a scale-down stabilization period started
        self.scale_down_stabilization_start: Dict[str, datetime] = {}

        # Ingested CI/CD event audit trail: ordered list of event dicts
        self.cicd_events: List[Dict[str, Any]] = []

        # Deduplication index: event_id -> UTC ISO timestamp
        self.processed_event_ids: Set[str] = set()

        # service_name -> latest processed event datetime (UTC) for out-of-order rejection
        self.last_event_timestamps: Dict[str, datetime] = {}

        # Load persisted state from disk if available
        if auto_load:
            self.load_from_disk()

    # ---------------------------------------------------------------------
    # Phase handling (Global & Per-Service)
    # ---------------------------------------------------------------------

    def set_phase(
        self,
        new_phase: DeploymentPhase,
        service_name: Optional[str] = None,
    ) -> None:
        """
        Set deployment phase globally or for a specific microservice.

        If service_name is specified, updates only that service's phase.
        If service_name is None, updates the global fallback phase.
        """
        now_utc = datetime.now(timezone.utc)
        with self._lock:
            if service_name:
                self.service_phases[service_name] = new_phase
                if new_phase == DeploymentPhase.ACTIVE_DEPLOYMENT:
                    self.deployment_start_times[service_name] = now_utc
                elif new_phase == DeploymentPhase.POST_DEPLOYMENT:
                    self.scale_down_stabilization_start[service_name] = now_utc
                elif new_phase == DeploymentPhase.NORMAL_OPERATION:
                    self.deployment_start_times.pop(service_name, None)
                    self.scale_down_stabilization_start.pop(service_name, None)
                logger.info(
                    "Service '%s' deployment phase transitioned to %s",
                    service_name,
                    new_phase.value,
                )
            else:
                self.phase = new_phase
                logger.info("Global deployment phase set to %s", new_phase.value)

            self.save_to_disk()

    def get_phase(self, service_name: Optional[str] = None) -> DeploymentPhase:
        """
        Retrieve deployment phase.

        If service_name is provided and has a specific phase recorded, returns that phase.
        Otherwise falls back to the global phase.
        """
        with self._lock:
            if service_name and service_name in self.service_phases:
                return self.service_phases[service_name]
            return self.phase

    def get_all_service_phases(self) -> Dict[str, str]:
        """Return a mapping of all recorded service phases."""
        with self._lock:
            return {svc: phase.value for svc, phase in self.service_phases.items()}

    def reset_service_phase(self, service_name: str) -> None:
        """Reset a service's phase to NORMAL_OPERATION."""
        self.set_phase(DeploymentPhase.NORMAL_OPERATION, service_name=service_name)

    # ---------------------------------------------------------------------
    # Cooldown handling
    # ---------------------------------------------------------------------

    def can_scale(self, service_name: str, now: datetime, config: ScalingConfig) -> bool:
        """Return True if the service is not within the global cooldown window."""
        with self._lock:
            last = self.last_action_time.get(service_name)
            if last is None:
                return True
            return (now - last).total_seconds() >= config.cooldown_sec

    def record_action(self, service_name: str, action: DecisionAction, now: datetime) -> None:
        """Record scaling action timestamp and update stabilization start."""
        with self._lock:
            self.last_action_time[service_name] = now
            self.last_action_type[service_name] = action.value
            if action == DecisionAction.SCALE_DOWN:
                self.scale_down_stabilization_start[service_name] = now
            else:
                self.scale_down_stabilization_start.pop(service_name, None)
            self.save_to_disk()

    def is_stabilized_for_scale_down(
        self,
        service_name: str,
        now: datetime,
        config: ScalingConfig,
    ) -> bool:
        """
        During POST_DEPLOYMENT a service may only scale down after a
        stabilization period defined by config.scale_down_stabilization_sec.
        """
        with self._lock:
            start = self.scale_down_stabilization_start.get(service_name)
            if start is None:
                return False
            return (now - start).total_seconds() >= config.scale_down_stabilization_sec

    # ---------------------------------------------------------------------
    # CI/CD Webhook Ingestion & Lifecycle Events
    # ---------------------------------------------------------------------

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """
        Verify HMAC SHA-256 signature for incoming CI/CD webhook requests.

        Supports standard headers like X-Hub-Signature-256 or X-CICD-Signature.
        Format can be 'sha256=<hex>' or raw '<hex>'.
        """
        if not signature_header:
            return False

        sig = signature_header.strip()
        if sig.startswith("sha256="):
            sig = sig[len("sha256="):]

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected.lower(), sig.lower())

    def record_cicd_event(
        self,
        event_data: Dict[str, Any],
        raw_body: bytes = b"",
        signature_header: Optional[str] = None,
        validate_signature: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate and ingest a CI/CD deployment lifecycle event.

        Expected event format:
        {
            "event_id": "evt-uuid-1234",
            "service_name": "checkoutservice",
            "event_type": "started" | "progressing" | "succeeded" | "failed" | "cancelled",
            "timestamp": "2026-11-11T12:00:00Z",
            "commit_sha": "abc1234",
            "image_tag": "v1.2.3",
            "pipeline_id": "pipe-99",
            "details": {...}
        }
        """
        # 1. Optional Signature Verification
        if validate_signature:
            if not signature_header or not self.verify_webhook_signature(raw_body, signature_header):
                logger.warning("Rejected CI/CD webhook: invalid or missing HMAC signature")
                return False, "Invalid or missing HMAC SHA-256 webhook signature", {}

        # 2. Basic Field Validation
        event_id = str(event_data.get("event_id") or "").strip()
        service_name = str(event_data.get("service_name") or "").strip()
        event_type = str(event_data.get("event_type") or "").strip().lower()
        raw_ts = event_data.get("timestamp")

        if not event_id:
            return False, "Missing required 'event_id' in CI/CD event", {}
        if not service_name:
            return False, "Missing required 'service_name' in CI/CD event", {}
        valid_types = {"started", "progressing", "succeeded", "failed", "cancelled"}
        if event_type not in valid_types:
            return False, f"Invalid 'event_type' '{event_type}'. Must be one of {valid_types}", {}

        # Parse timestamp (default to current UTC if absent or malformed)
        event_time: datetime
        if raw_ts:
            try:
                # Handle 'Z' suffix in Python < 3.11 compatibility
                clean_ts = raw_ts.replace("Z", "+00:00") if isinstance(raw_ts, str) else str(raw_ts)
                event_time = datetime.fromisoformat(clean_ts)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
            except Exception as exc:
                logger.warning("Malformed timestamp %s in event %s: %s", raw_ts, event_id, exc)
                return False, f"Malformed event timestamp: {raw_ts}", {}
        else:
            event_time = datetime.now(timezone.utc)

        with self._lock:
            # 3. Deduplication Check
            if event_id in self.processed_event_ids:
                logger.info("Ignoring duplicate CI/CD event '%s'", event_id)
                return False, f"Duplicate event '{event_id}' previously processed", {"event_id": event_id}

            # 4. Out-of-Order / Stale Event Rejection
            last_ts = self.last_event_timestamps.get(service_name)
            if last_ts is not None and event_time < last_ts:
                logger.warning(
                    "Rejected out-of-order CI/CD event %s for %s (ts %s < last %s)",
                    event_id,
                    service_name,
                    event_time.isoformat(),
                    last_ts.isoformat(),
                )
                return (
                    False,
                    f"Out-of-order event rejected: event time {event_time.isoformat()} is older than last processed {last_ts.isoformat()}",
                    {"event_id": event_id, "service_name": service_name},
                )

            # 5. Record Event & Update State
            self.processed_event_ids.add(event_id)
            self.last_event_timestamps[service_name] = event_time

            previous_phase = self.get_phase(service_name)
            new_phase = previous_phase

            if event_type == "started":
                new_phase = DeploymentPhase.ACTIVE_DEPLOYMENT
                self.service_phases[service_name] = new_phase
                self.deployment_start_times[service_name] = event_time
            elif event_type == "progressing":
                new_phase = DeploymentPhase.ACTIVE_DEPLOYMENT
                self.service_phases[service_name] = new_phase
            elif event_type == "succeeded":
                new_phase = DeploymentPhase.POST_DEPLOYMENT
                self.service_phases[service_name] = new_phase
                self.scale_down_stabilization_start[service_name] = event_time
            elif event_type in ("failed", "cancelled"):
                new_phase = DeploymentPhase.NORMAL_OPERATION
                self.service_phases[service_name] = new_phase
                self.deployment_start_times.pop(service_name, None)
                self.scale_down_stabilization_start.pop(service_name, None)

            recorded_event = {
                "event_id": event_id,
                "service_name": service_name,
                "event_type": event_type,
                "timestamp": event_time.isoformat(),
                "previous_phase": previous_phase.value,
                "new_phase": new_phase.value,
                "commit_sha": event_data.get("commit_sha", ""),
                "image_tag": event_data.get("image_tag", ""),
                "pipeline_id": event_data.get("pipeline_id", ""),
                "details": event_data.get("details", {}),
            }

            self.cicd_events.append(recorded_event)
            # Bound audit log to latest 200 events
            if len(self.cicd_events) > 200:
                self.cicd_events = self.cicd_events[-200:]

            self.save_to_disk()

            logger.info(
                "Processed CI/CD event '%s' (%s) for '%s': %s -> %s",
                event_id,
                event_type,
                service_name,
                previous_phase.value,
                new_phase.value,
            )
            return True, f"Event '{event_id}' processed successfully", recorded_event

    def get_cicd_events(self, limit: int = 50, service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recorded CI/CD event history ordered latest first."""
        with self._lock:
            events = self.cicd_events
            if service_name:
                events = [e for e in events if e.get("service_name") == service_name]
            return list(reversed(events[-limit:]))

    # ---------------------------------------------------------------------
    # Kubernetes Rollout Reconciliation
    # ---------------------------------------------------------------------

    def reconcile_kubernetes_rollout(
        self,
        service_name: str,
        rollout_info: Dict[str, Any],
        config: Optional[ScalingConfig] = None,
    ) -> Dict[str, Any]:
        """
        Reconcile deployment state using live Kubernetes Deployment rollout status.

        Expected rollout_info structure:
        {
            "generation": 2,
            "observed_generation": 2,
            "desired_replicas": 1,
            "updated_replicas": 1,
            "available_replicas": 1,
            "ready_replicas": 1,
            "unavailable_replicas": 0,
            "conditions": [
                {"type": "Progressing", "status": "True", "reason": "NewReplicaSetAvailable"},
                {"type": "Available", "status": "True", "reason": "MinimumReplicasAvailable"}
            ]
        }
        """
        cfg_obj = config or ScalingConfig()
        now_utc = datetime.now(timezone.utc)

        with self._lock:
            current_phase = self.get_phase(service_name)
            generation = rollout_info.get("generation", 0)
            observed_gen = rollout_info.get("observed_generation", 0)
            desired = rollout_info.get("desired_replicas", 1)
            updated = rollout_info.get("updated_replicas", 0)
            available = rollout_info.get("available_replicas", 0)
            conditions = rollout_info.get("conditions", [])

            # Check for rollout failure condition
            rollout_failed = False
            failure_reason = ""
            for cond in conditions:
                if cond.get("type") == "Progressing":
                    if cond.get("status") == "False" and cond.get("reason") == "ProgressDeadlineExceeded":
                        rollout_failed = True
                        failure_reason = cond.get("message", "ProgressDeadlineExceeded")
                        break

            new_phase = current_phase
            reconciliation_action = "NO_CHANGE"

            if rollout_failed:
                # Rollout stalled or exceeded deadline -> revert phase to NORMAL_OPERATION
                new_phase = DeploymentPhase.NORMAL_OPERATION
                self.service_phases[service_name] = new_phase
                self.deployment_start_times.pop(service_name, None)
                self.scale_down_stabilization_start.pop(service_name, None)
                reconciliation_action = "FAILED_ROLLOUT_RESET"
                logger.warning(
                    "Reconciled service %s rollout failure (%s) -> NORMAL_OPERATION",
                    service_name,
                    failure_reason,
                )

            elif generation > 0 and observed_gen > 0 and generation != observed_gen:
                # Generation mismatch: a new deployment revision is actively rolling out
                if current_phase != DeploymentPhase.ACTIVE_DEPLOYMENT:
                    new_phase = DeploymentPhase.ACTIVE_DEPLOYMENT
                    self.service_phases[service_name] = new_phase
                    self.deployment_start_times.setdefault(service_name, now_utc)
                    reconciliation_action = "DETECTED_ACTIVE_ROLLOUT"

            elif updated < desired:
                # Still updating replica sets
                if current_phase != DeploymentPhase.ACTIVE_DEPLOYMENT:
                    new_phase = DeploymentPhase.ACTIVE_DEPLOYMENT
                    self.service_phases[service_name] = new_phase
                    self.deployment_start_times.setdefault(service_name, now_utc)
                    reconciliation_action = "DETECTED_UPDATING_REPLICAS"

            elif observed_gen == generation and updated >= desired and available >= desired and desired > 0:
                # Rollout is fully complete
                if current_phase == DeploymentPhase.ACTIVE_DEPLOYMENT:
                    new_phase = DeploymentPhase.POST_DEPLOYMENT
                    self.service_phases[service_name] = new_phase
                    self.scale_down_stabilization_start[service_name] = now_utc
                    reconciliation_action = "TRANSITION_TO_POST_DEPLOYMENT"
                    logger.info("Service %s rollout complete -> POST_DEPLOYMENT", service_name)
                elif current_phase == DeploymentPhase.POST_DEPLOYMENT:
                    # Check if post-deployment stabilization duration has expired
                    stab_start = self.scale_down_stabilization_start.get(service_name)
                    if stab_start:
                        elapsed = (now_utc - stab_start).total_seconds()
                        if elapsed >= cfg_obj.scale_down_stabilization_sec:
                            new_phase = DeploymentPhase.NORMAL_OPERATION
                            self.service_phases[service_name] = new_phase
                            self.scale_down_stabilization_start.pop(service_name, None)
                            self.deployment_start_times.pop(service_name, None)
                            reconciliation_action = "STABILIZATION_COMPLETE_TO_NORMAL"
                            logger.info(
                                "Service %s stabilization window elapsed (%.1fs) -> NORMAL_OPERATION",
                                service_name,
                                elapsed,
                            )

            if reconciliation_action != "NO_CHANGE":
                self.save_to_disk()

            return {
                "service_name": service_name,
                "previous_phase": current_phase.value,
                "reconciled_phase": new_phase.value,
                "action": reconciliation_action,
                "rollout_failed": rollout_failed,
                "failure_reason": failure_reason,
                "generation": generation,
                "observed_generation": observed_gen,
                "desired_replicas": desired,
                "updated_replicas": updated,
                "available_replicas": available,
                "timestamp": now_utc.isoformat(),
            }

    # ---------------------------------------------------------------------
    # Durable State Persistence (Atomic JSON)
    # ---------------------------------------------------------------------

    def save_to_disk(self, filepath: Optional[str] = None) -> bool:
        """Atomically persist deployment state and event history to JSON on disk."""
        target_path = filepath or self.persistence_file
        with self._lock:
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                payload = {
                    "version": "1.0",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "global_phase": self.phase.value,
                    "service_phases": {
                        svc: phase.value for svc, phase in self.service_phases.items()
                    },
                    "deployment_start_times": {
                        svc: dt.isoformat() for svc, dt in self.deployment_start_times.items()
                    },
                    "last_action_time": {
                        svc: dt.isoformat() for svc, dt in self.last_action_time.items()
                    },
                    "last_action_type": self.last_action_type,
                    "scale_down_stabilization_start": {
                        svc: dt.isoformat()
                        for svc, dt in self.scale_down_stabilization_start.items()
                    },
                    "last_event_timestamps": {
                        svc: dt.isoformat()
                        for svc, dt in self.last_event_timestamps.items()
                    },
                    "processed_event_ids": list(self.processed_event_ids),
                    "cicd_events": self.cicd_events[-100:],
                }

                # Atomic write: write to temp file in same directory then replace
                dir_name = os.path.dirname(target_path)
                with tempfile.NamedTemporaryFile(
                    "w",
                    dir=dir_name,
                    delete=False,
                    encoding="utf-8",
                ) as tmp_file:
                    json.dump(payload, tmp_file, indent=2)
                    tmp_name = tmp_file.name

                os.replace(tmp_name, target_path)
                return True
            except Exception as exc:
                logger.error("Failed to persist deployment state to %s: %s", target_path, exc)
                return False

    def load_from_disk(self, filepath: Optional[str] = None) -> bool:
        """Load deployment state and event history from disk if present."""
        target_path = filepath or self.persistence_file
        with self._lock:
            if not os.path.exists(target_path):
                return False

            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                # Global phase
                global_phase_str = payload.get("global_phase")
                if global_phase_str:
                    try:
                        self.phase = DeploymentPhase(global_phase_str)
                    except ValueError:
                        pass

                # Per-service phases
                raw_service_phases = payload.get("service_phases", {})
                for svc, phase_str in raw_service_phases.items():
                    try:
                        self.service_phases[svc] = DeploymentPhase(phase_str)
                    except ValueError:
                        pass

                # Deployment start times
                for svc, ts_str in payload.get("deployment_start_times", {}).items():
                    try:
                        self.deployment_start_times[svc] = datetime.fromisoformat(ts_str)
                    except Exception:
                        pass

                # Last action times
                for svc, ts_str in payload.get("last_action_time", {}).items():
                    try:
                        self.last_action_time[svc] = datetime.fromisoformat(ts_str)
                    except Exception:
                        pass

                self.last_action_type = payload.get("last_action_type", {})

                # Stabilization start times
                for svc, ts_str in payload.get("scale_down_stabilization_start", {}).items():
                    try:
                        self.scale_down_stabilization_start[svc] = datetime.fromisoformat(ts_str)
                    except Exception:
                        pass

                # Event timestamps
                for svc, ts_str in payload.get("last_event_timestamps", {}).items():
                    try:
                        self.last_event_timestamps[svc] = datetime.fromisoformat(ts_str)
                    except Exception:
                        pass

                # Deduplication IDs
                self.processed_event_ids = set(payload.get("processed_event_ids", []))

                # CI/CD events
                self.cicd_events = payload.get("cicd_events", [])

                logger.info(
                    "Successfully loaded deployment state from %s (%d services, %d events)",
                    target_path,
                    len(self.service_phases),
                    len(self.cicd_events),
                )
                return True
            except Exception as exc:
                logger.error("Failed to load deployment state from %s: %s", target_path, exc)
                return False
