# backend/scripts/analyze_experiment_results.py
"""
Result‑analysis utility for DPBPS experiments.
It scans a root directory for experiment sub‑folders containing
`summary.json`, optional `config.json`, and Locust CSV stats. It produces
- a consolidated JSON list (`experiment_summary.json`)
- a CSV table (`experiment_summary.csv`)
- a short Markdown report (`experiment_report.md`)
Simulation and real‑HTTP experiments are kept separate.
Missing metrics stay `null`.
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def _load_summaries(root: Path) -> List[Dict]:
    """Collect every `summary.json` under *root* (recursive)."""
    summaries: List[Dict] = []
    for summary_path in root.rglob("summary.json"):
        try:
            summaries.append(json.loads(summary_path.read_text()))
        except Exception:
            # malformed – still record path for debugging
            summaries.append({"experiment_id": summary_path.parent.name, "error": "malformed_summary"})
    return summaries


def _enrich_with_config_and_metrics(summaries: List[Dict], root: Path) -> None:
    """Add `config` and `metrics` keys to each summary dict when files exist.
    `metrics` are extracted from Locust's CSV output if present.
    """
    for s in summaries:
        exp_dir = root / s.get("experiment_id", "")
        cfg_path = exp_dir / "config.json"
        if cfg_path.is_file():
            s["config"] = json.loads(cfg_path.read_text())
        csv_path = exp_dir / "locust_stats.csv"
        if csv_path.is_file():
            try:
                with csv_path.open() as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if rows:
                        last = rows[-1]
                        s["metrics"] = {
                            "total_requests": int(last.get("Request Count", 0) or 0),
                            "successful_requests": int(last.get("Success", 0) or 0),
                            "failed_requests": int(last.get("Failure", 0) or 0),
                            "median_latency_ms": float(last.get("Median Response Time", 0) or 0),
                            "p95_latency_ms": float(last.get("95th percentile", 0) or 0),
                            "p99_latency_ms": float(last.get("99th percentile", 0) or 0),
                        }
            except Exception:
                s["metrics"] = {}
        else:
            s["metrics"] = {}


def _write_csv(summaries: List[Dict], out_path: Path) -> None:
    fieldnames = [
        "experiment_id",
        "classification",
        "duration_seconds",
        "request_rate",
        "initial_replicas",
        "total_requests",
        "successful_requests",
        "failed_requests",
        "median_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for s in summaries:
            cfg = s.get("config", {})
            met = s.get("metrics", {})
            writer.writerow({
                "experiment_id": s.get("experiment_id"),
                "classification": s.get("classification"),
                "duration_seconds": cfg.get("duration_seconds"),
                "request_rate": cfg.get("request_rate"),
                "initial_replicas": cfg.get("initial_replicas"),
                "total_requests": met.get("total_requests"),
                "successful_requests": met.get("successful_requests"),
                "failed_requests": met.get("failed_requests"),
                "median_latency_ms": met.get("median_latency_ms"),
                "p95_latency_ms": met.get("p95_latency_ms"),
                "p99_latency_ms": met.get("p99_latency_ms"),
            })


def _write_markdown(summaries: List[Dict], out_path: Path) -> None:
    lines = ["# DPBPS Experiment Analysis", ""]
    sim = [s for s in summaries if s.get("classification") == "simulation"]
    real = [s for s in summaries if s.get("classification") == "real_http_load_test"]
    lines.append("## Simulation experiments")
    for s in sim:
        lines.append(f"* **{s.get('experiment_id')}** – {s.get('config', {}).get('profile', 'N/A')}")
    lines.append("")
    lines.append("## Real‑HTTP load‑test experiments")
    for s in real:
        cfg = s.get("config", {})
        met = s.get("metrics", {})
        lines.append(f"### {s.get('experiment_id')}")
        lines.append(f"- Profile: {cfg.get('profile', 'N/A')}")
        lines.append(f"- Duration: {cfg.get('duration_seconds', 'N/A')} s")
        lines.append(f"- Request rate: {cfg.get('request_rate', 'N/A')} RPS")
        lines.append(f"- Total requests: {met.get('total_requests', 'N/A')}")
        lines.append(f"- Successful: {met.get('successful_requests', 'N/A')}")
        lines.append(f"- Median latency: {met.get('median_latency_ms', 'N/A')} ms")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze DPBPS experiment results")
    parser.add_argument("--results-dir", default="results/experiments", help="Root experiments directory")
    parser.add_argument("--output-dir", default="results/analysis", help="Where to write reports")
    args = parser.parse_args()

    root = Path(args.results_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = _load_summaries(root)
    _enrich_with_config_and_metrics(summaries, root)
    _write_json = lambda p, d: p.write_text(json.dumps(d, indent=2))
    _write_json(out_dir / "experiment_summary.json", summaries)
    _write_csv(summaries, out_dir / "experiment_summary.csv")
    _write_markdown(summaries, out_dir / "experiment_report.md")
    print(f"Analysis written to {out_dir}")

if __name__ == "__main__":
    main()
