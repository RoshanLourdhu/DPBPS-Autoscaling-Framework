import argparse
import datetime
import json
import sys
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List

from backend.scripts.check_readiness import run as check_readiness

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DPBPS or fixed‑replica experiment")
    parser.add_argument("--profile", required=True, choices=["normal_operation", "pre_deployment", "post_deployment"], help="Workload profile")
    parser.add_argument("--approach", required=True, choices=["fixed", "dpbps", "simulation"], help="Experiment type")
    parser.add_argument("--duration", type=int, default=60, help="Experiment duration seconds")
    parser.add_argument("--rate", type=int, default=5, help="Target request rate (RPS)")
    parser.add_argument("--initial-replicas", type=int, default=2, help="Initial replica count")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of repeats")
    parser.add_argument("--out-dir", default="results/experiments", help="Root output directory")
    return parser.parse_args()

def _make_exp_dir(root: Path) -> Path:
    uid = uuid.uuid4().hex
    # Use a Windows‑compatible timestamp (replace ':' with '-')
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    d = root / f"{ts}_{uid}"
    d.mkdir(parents=True, exist_ok=False)
    return d

def _write_json(p: Path, data: Dict) -> None:
    p.write_text(json.dumps(data, indent=2))

def _run_locust(host: str, duration: int, rate: int, out_dir: Path) -> int:
    cmd = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        "backend/load_testing/locustfile.py",
        "--headless",
        f"--users={rate}",
        f"--spawn-rate={rate}",
        f"--run-time={duration}s",
        f"--host={host}",
        f"--csv={out_dir / 'locust'}",
        "--csv-full-history",
    ]
    result = subprocess.run(cmd, cwd=Path.cwd())
    return result.returncode

def main() -> None:
    args = _parse_args()
    # readiness check
    try:
        readiness = check_readiness()
    except Exception:
        sys.exit(1)

    out_root = Path(args.out_dir).expanduser().resolve()
    exp_dir = _make_exp_dir(out_root)

    config = {
        "experiment_id": exp_dir.name,
        "profile": args.profile,
        "approach": args.approach,
        "duration_seconds": args.duration,
        "request_rate": args.rate,
        "initial_replicas": args.initial_replicas,
        "repetitions": args.repetitions,
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
    }
    _write_json(exp_dir / "config.json", config)
    _write_json(exp_dir / "readiness.json", readiness)

    classification = "unsupported"
    if args.approach == "simulation":
        # reuse existing simulation results if any
        sim_dir = Path("results/simulation")
        if sim_dir.is_dir():
            latest = max(sim_dir.iterdir(), key=lambda p: p.stat().st_mtime)
            for f in latest.iterdir():
                (exp_dir / f.name).write_bytes(f.read_bytes())
            classification = "simulation"
    elif args.approach in ("fixed", "dpbps"):
        host = "http://localhost:8000"
        rc = _run_locust(host, args.duration, args.rate, exp_dir)
        classification = "real_http_load_test" if rc == 0 else "failed"
    else:
        classification = "unsupported"

    summary = {
        "experiment_id": exp_dir.name,
        "classification": classification,
        "config_path": str(exp_dir / "config.json"),
        "readiness_path": str(exp_dir / "readiness.json"),
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
    }
    _write_json(exp_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
