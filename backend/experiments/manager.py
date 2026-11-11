"""
Experiment management and recording engine for DPBPS.

Provides:
1. Unique experiment ID generation.
2. Experiment metadata creation and lifecycle management.
3. State machine validation (enforcing legal state transitions).
4. Strict safety lock: execution in Stage 7 is permanently blocked.
5. Storage management persisting metadata to results/experiments/.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.workload.models import (
    WorkloadProfileConfig,
    WorkloadProfileName,
)
from backend.workload.profiles import get_profile
from backend.workload.validation import validate_workload_config
from .models import (
    VALID_STATE_TRANSITIONS,
    ExperimentMetadata,
    ExperimentStatus,
)
from .metrics import (
    ExperimentMetricSnapshot,
    ExperimentMetricsCollection,
)

logger = logging.getLogger(__name__)


# Default experiments output directory (matches existing results/experiments)
DEFAULT_EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "experiments"


class ExperimentManager:
    """
    Manages experiment metadata, lifecycle, and telemetry recordings.
    
    Safety Invariants:
    - In Stage 7, experiments cannot be started (status RUNNING is forbidden).
    - Invalid state transitions are rejected with descriptive exceptions.
    - Missing telemetry is never fabricated.
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = storage_dir or DEFAULT_EXPERIMENTS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._experiments: Dict[str, ExperimentMetadata] = {}
        self._metrics_store: Dict[str, ExperimentMetricsCollection] = {}
        self._load_existing_experiments()

    def _load_existing_experiments(self) -> None:
        """Scan storage directory and ingest existing experiment metadata."""
        if not self.storage_dir.exists():
            return

        for item in self.storage_dir.iterdir():
            if not item.is_dir():
                continue
            meta_file = item / "metadata.json"
            config_file = item / "config.json"
            try:
                if meta_file.exists():
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    exp = ExperimentMetadata(**data)
                    self._experiments[exp.experiment_id] = exp
                elif config_file.exists():
                    # Legacy or previous experiment format
                    cdata = json.loads(config_file.read_text(encoding="utf-8"))
                    exp_id = cdata.get("experiment_id", item.name)
                    prof_name = cdata.get("profile", "NORMAL_TRAFFIC").upper()
                    # Map legacy names if necessary
                    if prof_name == "NORMAL_OPERATION":
                        prof_name = "NORMAL_TRAFFIC"
                    profile_cfg = get_profile(prof_name) or get_profile("NORMAL_TRAFFIC")
                    
                    exp = ExperimentMetadata(
                        experiment_id=exp_id,
                        profile_name=profile_cfg.profile_name,
                        configuration=profile_cfg,
                        created_at=cdata.get("timestamp_utc", datetime.now(timezone.utc).isoformat()),
                        status=ExperimentStatus.COMPLETED,
                        selected_concurrency=cdata.get("request_rate", 10),
                        execution_disabled=True,
                        notes=f"Ingested legacy experiment from {item.name}",
                    )
                    self._experiments[exp_id] = exp
            except Exception as e:
                logger.warning("Could not load experiment from %s: %s", item, e)

    def generate_experiment_id(self, profile_name: WorkloadProfileName) -> str:
        """Generate a collision-resistant, human-readable experiment ID."""
        now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        uid_short = uuid.uuid4().hex[:8]
        return f"exp_{now_str}_{profile_name.value.lower()}_{uid_short}"

    def create_experiment(
        self,
        profile_name: WorkloadProfileName,
        custom_configuration: Optional[WorkloadProfileConfig] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> ExperimentMetadata:
        """
        Create and record a new prepared experiment.
        
        Initial status: CREATED.
        Execution remains strictly disabled.
        """
        # Determine configuration
        config = custom_configuration or get_profile(profile_name)
        if config is None:
            raise ValueError(f"Unknown workload profile: '{profile_name}'")

        # Validate configuration safety
        is_valid, errors = validate_workload_config(config)
        if not is_valid:
            raise ValueError(f"Workload configuration violates safety envelopes: {errors}")

        exp_id = self.generate_experiment_id(profile_name)
        now_utc = datetime.now(timezone.utc).isoformat()

        metadata = ExperimentMetadata(
            experiment_id=exp_id,
            profile_name=profile_name,
            configuration=config,
            application_entry_point=f"http://{config.target_host}",
            created_at=now_utc,
            status=ExperimentStatus.CREATED,
            selected_concurrency=config.users,
            target_request_rate=config.custom_parameters.get("target_rps_approx"),
            actual_observed_request_rate=None,
            failure_information=None,
            execution_disabled=True,  # STRICT SAFETY GUARD
            tags=tags or ["dpbps-evaluation", profile_name.value.lower()],
            notes=notes,
        )

        self._experiments[exp_id] = metadata
        self._persist_experiment(metadata)
        logger.info("Created experiment record: %s (profile=%s)", exp_id, profile_name.value)
        return metadata

    def update_status(
        self,
        experiment_id: str,
        new_status: ExperimentStatus,
        failure_information: Optional[str] = None,
    ) -> ExperimentMetadata:
        """
        Transition an experiment to a new status according to state machine rules.
        
        STRICT SAFETY ENFORCEMENT:
        Attempting to transition to RUNNING in Stage 7 immediately raises RuntimeError.
        """
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise KeyError(f"Experiment '{experiment_id}' not found")

        # SAFETY LOCK: Execution is strictly disabled unless EXPERIMENT_EXECUTION_ENABLED is True
        if new_status == ExperimentStatus.RUNNING and os.getenv("EXPERIMENT_EXECUTION_ENABLED", "false").lower() != "true":
            raise RuntimeError(
                "Workload execution is strictly DISABLED in Stage 7. "
                "Experiments may only be prepared in CREATED or READY status."
            )

        # Validate legal transition
        allowed = VALID_STATE_TRANSITIONS.get(exp.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid state transition for experiment '{experiment_id}': "
                f"cannot move from {exp.status.value} to {new_status.value}"
            )

        exp.status = new_status
        if failure_information:
            exp.failure_information = failure_information

        if new_status == ExperimentStatus.RUNNING:
            exp.start_timestamp = datetime.now(timezone.utc).isoformat()
            exp.execution_disabled = False

        if new_status in (ExperimentStatus.COMPLETED, ExperimentStatus.STOPPED, ExperimentStatus.FAILED):
            exp.end_timestamp = datetime.now(timezone.utc).isoformat()

        self._persist_experiment(exp)
        return exp

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentMetadata]:
        """Retrieve metadata for a specific experiment ID."""
        return self._experiments.get(experiment_id)

    def list_experiments(self, limit: int = 50) -> List[ExperimentMetadata]:
        """List experiments sorted with most recent first."""
        sorted_exps = sorted(
            self._experiments.values(),
            key=lambda x: x.created_at,
            reverse=True,
        )
        return sorted_exps[:limit]

    def get_metrics(self, experiment_id: str) -> Optional[ExperimentMetricsCollection]:
        """Retrieve recorded metric snapshots for an experiment."""
        return self._metrics_store.get(experiment_id)

    def record_snapshot(self, experiment_id: str, snapshot: ExperimentMetricSnapshot) -> None:
        """Append a metric snapshot to an experiment."""
        if experiment_id not in self._metrics_store:
            exp = self._experiments.get(experiment_id)
            prof_name = exp.profile_name.value if exp else "UNKNOWN"
            self._metrics_store[experiment_id] = ExperimentMetricsCollection(
                experiment_id=experiment_id,
                profile_name=prof_name,
                start_timestamp=snapshot.timestamp_utc,
            )

        collection = self._metrics_store[experiment_id]
        collection.snapshots.append(snapshot)
        collection.total_snapshots = len(collection.snapshots)
        collection.end_timestamp = snapshot.timestamp_utc

    def _persist_experiment(self, metadata: ExperimentMetadata) -> None:
        """Write experiment metadata and configuration to storage directory."""
        exp_dir = self.storage_dir / metadata.experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Write config.json
        config_path = exp_dir / "config.json"
        config_path.write_text(
            metadata.configuration.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Write metadata.json
        meta_path = exp_dir / "metadata.json"
        meta_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

