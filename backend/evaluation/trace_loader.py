"""
Trace loader for empirical experiment datasets (E01 - E06).
Normalizes raw telemetry snapshots into standardized evaluation schemas.
"""

import os
import json
from typing import Dict, List, Tuple
from .models import NormalizedObservation


SERVICES_10 = [
    "frontend",
    "cartservice",
    "productcatalogservice",
    "currencyservice",
    "paymentservice",
    "shippingservice",
    "emailservice",
    "checkoutservice",
    "recommendationservice",
    "adservice"
]

EXPERIMENT_CATALOG = {
    "E01": {
        "id": "exp_20261110T152425_normal_traffic_838109a5",
        "profile": "NORMAL_TRAFFIC",
        "display_name": "E01: Normal Traffic Baseline"
    },
    "E02": {
        "id": "exp_20261110T165351_gradual_traffic_increase_309b2d79",
        "profile": "GRADUAL_TRAFFIC_INCREASE",
        "display_name": "E02: Gradual Traffic Increase"
    },
    "E03": {
        "id": "exp_20261110T170244_sudden_traffic_spike_d80c4694",
        "profile": "SUDDEN_TRAFFIC_SPIKE",
        "display_name": "E03: Sudden Traffic Spike"
    },
    "E04": {
        "id": "exp_20261110T172135_sustained_high_traffic_51ce3165",
        "profile": "SUSTAINED_HIGH_TRAFFIC",
        "display_name": "E04: Sustained High Traffic"
    },
    "E05": {
        "id": "exp_20261110T172806_traffic_decrease_71144bfe",
        "profile": "TRAFFIC_DECREASE",
        "display_name": "E05: Traffic Decrease"
    },
    "E06": {
        "id": "exp_20261110T173312_bursty_traffic_55733a14",
        "profile": "BURSTY_TRAFFIC",
        "display_name": "E06: Bursty Traffic"
    }
}


class TraceLoader:
    """Loads and normalizes telemetry traces and decision logs from disk."""

    def __init__(self, base_dir: str = r"D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments"):
        self.base_dir = base_dir

    def load_experiment_trace(self, exp_code: str) -> Tuple[List[NormalizedObservation], Dict[str, List[dict]], dict]:
        """
        Load an experiment's telemetry and empirical decisions.
        
        Returns:
            Tuple of (observations, empirical_decisions_by_service, experiment_metadata)
        """
        if exp_code not in EXPERIMENT_CATALOG:
            raise ValueError(f"Unknown experiment code: {exp_code}. Expected one of {list(EXPERIMENT_CATALOG.keys())}")

        meta = EXPERIMENT_CATALOG[exp_code]
        eid = meta["id"]
        exp_path = os.path.join(self.base_dir, eid)

        if not os.path.exists(exp_path):
            raise FileNotFoundError(f"Experiment directory not found: {exp_path}")

        # 1. Load telemetry metrics
        telem_file = os.path.join(exp_path, "telemetry_metrics.json")
        with open(telem_file, "r") as f:
            raw_telem = json.load(f)

        raw_snapshots = raw_telem.get("snapshots", []) if isinstance(raw_telem, dict) else raw_telem

        # 2. Load empirical decisions
        dec_file = os.path.join(exp_path, "dpbps_decisions.json")
        empirical_decisions: Dict[str, List[dict]] = {s: [] for s in SERVICES_10}

        if os.path.exists(dec_file):
            with open(dec_file, "r") as f:
                raw_dec = json.load(f)
            evals = raw_dec.get("evaluations", []) if isinstance(raw_dec, dict) else raw_dec
            for ev in evals:
                ev_time = ev.get("timestamp")
                decs = ev.get("decisions", [])
                for d in decs:
                    svc = d.get("service_name")
                    if svc in empirical_decisions:
                        empirical_decisions[svc].append({
                            "timestamp": ev_time,
                            "action": d.get("action") or d.get("decision_type", "HOLD"),
                            "current_replicas": d.get("current_replicas", 1),
                            "target_replicas": d.get("target_replicas", 1),
                            "reason": d.get("reason", ""),
                            "is_bottleneck": d.get("is_bottleneck", False),
                            "priority_score": d.get("priority_score"),
                            "trigger_metric": d.get("trigger_metric"),
                            "metric_value": d.get("metric_value")
                        })

        # 3. Normalize snapshots into list of NormalizedObservation
        observations: List[NormalizedObservation] = []
        for snap_idx, snap in enumerate(raw_snapshots):
            ts = snap.get("timestamp", "")
            elapsed = snap.get("elapsed_seconds", float(snap_idx * 10))
            stage = snap.get("stage")
            services_dict = snap.get("services", {})

            for svc in SERVICES_10:
                if svc not in services_dict:
                    # Unpopulated / missing service observation
                    obs = NormalizedObservation(
                        experiment_id=eid,
                        service_name=svc,
                        timestamp=ts,
                        elapsed_seconds=elapsed,
                        stage=stage,
                        telemetry_available=False
                    )
                else:
                    sd = services_dict[svc]
                    avail = sd.get("telemetry_available", True)
                    obs = NormalizedObservation(
                        experiment_id=eid,
                        service_name=svc,
                        timestamp=ts,
                        elapsed_seconds=elapsed,
                        stage=stage,
                        request_rate=float(sd.get("request_rate") or 0.0),
                        p50_latency_ms=sd.get("p50_latency_ms"),
                        p95_latency_ms=sd.get("p95_latency_ms"),
                        p99_latency_ms=sd.get("p99_latency_ms"),
                        error_rate=float(sd.get("error_rate") or 0.0),
                        cpu_usage_millicores=float(sd.get("cpu_usage_millicores") or 0.0),
                        memory_usage_mib=float(sd.get("memory_usage_mib") or 0.0),
                        cpu_utilization_ratio=float(sd.get("cpu_utilization_ratio") or sd.get("cpu_utilisation") or 0.0),
                        memory_utilization_ratio=float(sd.get("memory_utilization_ratio") or sd.get("memory_utilisation") or 0.0),
                        current_replicas=int(sd.get("desired_replicas") or sd.get("current_replicas") or 1),
                        ready_replicas=sd.get("ready_replicas"),
                        telemetry_available=avail,
                        dependencies=sd.get("dependencies", []),
                        deployment_phase=sd.get("deployment_phase", "NORMAL_OPERATION")
                    )

                # Attach matching empirical decision metadata if present
                svc_decs = empirical_decisions.get(svc, [])
                if snap_idx < len(svc_decs):
                    svc_decs[snap_idx]["elapsed_seconds"] = elapsed

                observations.append(obs)

        return observations, empirical_decisions, meta

