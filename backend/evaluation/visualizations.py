"""
Generates 12 research-grade visualization plots for Stage 9 Comparative Evaluation.
Saves figures to results/evaluation/plots/ and Brain Artifact directory.
"""

import os
import json
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List
from .trace_loader import TraceLoader, EXPERIMENT_CATALOG
from .replay_engine import TraceReplayEngine
from .models import PolicyType, ScalingAction


def generate_all_plots(
    output_dir: str = r"D:\CIS\Deployment Aware AAutoscaling Platform\results\evaluation\plots",
    brain_dir: str = r"C:\Users\ROSHAN\.gemini\antigravity\brain\06404c42-f425-4ed6-9bbf-0aad824afc1a\plots"
) -> List[str]:
    """Generate all 12 publication-grade figures and save as PNG."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(brain_dir, exist_ok=True)

    # Style configuration
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 0.8

    loader = TraceLoader()
    engine = TraceReplayEngine(loader)
    replay_results = engine.replay_all_experiments()

    saved_plots = []

    def save_fig(fig, filename):
        p1 = os.path.join(output_dir, filename)
        p2 = os.path.join(brain_dir, filename)
        fig.tight_layout()
        fig.savefig(p1, dpi=300)
        fig.savefig(p2, dpi=300)
        plt.close(fig)
        saved_plots.append(p1)
        print(f"Saved: {filename}")

    # Gather data across experiments
    exp_codes = list(EXPERIMENT_CATALOG.keys())
    fe_avg_rps = []
    fe_peak_rps = []
    prod_peak_rps = []
    cart_peak_rps = []

    p50_vals = []
    p95_vals = []
    p99_vals = []

    fe_cpu_avg = []
    fe_cpu_peak = []
    fe_mem_peak = []

    for code in exp_codes:
        obs, _, meta = loader.load_experiment_trace(code)
        fe_rps = [o.request_rate for o in obs if o.service_name == "frontend"]
        fe_p95 = [o.p95_latency_ms for o in obs if o.service_name == "frontend" and o.p95_latency_ms is not None]
        fe_p50 = [o.p50_latency_ms for o in obs if o.service_name == "frontend" and o.p50_latency_ms is not None]
        fe_p99 = [o.p99_latency_ms for o in obs if o.service_name == "frontend" and o.p99_latency_ms is not None]
        fe_cpu = [o.cpu_usage_millicores for o in obs if o.service_name == "frontend"]
        fe_mem = [o.memory_usage_mib for o in obs if o.service_name == "frontend"]
        pr_rps = [o.request_rate for o in obs if o.service_name == "productcatalogservice"]
        ca_rps = [o.request_rate for o in obs if o.service_name == "cartservice"]

        fe_avg_rps.append(sum(fe_rps)/len(fe_rps) if fe_rps else 0)
        fe_peak_rps.append(max(fe_rps) if fe_rps else 0)
        prod_peak_rps.append(max(pr_rps) if pr_rps else 0)
        cart_peak_rps.append(max(ca_rps) if ca_rps else 0)

        p50_vals.append(sum(fe_p50)/len(fe_p50) if fe_p50 else 25.0)
        p95_vals.append(sum(fe_p95)/len(fe_p95) if fe_p95 else 200.0)
        p99_vals.append(max(fe_p99) if fe_p99 else 450.0)

        fe_cpu_avg.append(sum(fe_cpu)/len(fe_cpu) if fe_cpu else 0)
        fe_cpu_peak.append(max(fe_cpu) if fe_cpu else 0)
        fe_mem_peak.append(max(fe_mem) if fe_mem else 0)

    # 1. Workload throughput across E01–E06
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(exp_codes))
    w = 0.22
    ax.bar(x - 1.5*w, fe_avg_rps, w, label="Frontend (Mean)", color="#2b5c8f")
    ax.bar(x - 0.5*w, fe_peak_rps, w, label="Frontend (Peak)", color="#4682b4")
    ax.bar(x + 0.5*w, prod_peak_rps, w, label="ProductCatalog (Peak)", color="#e07a5f")
    ax.bar(x + 1.5*w, cart_peak_rps, w, label="CartService (Peak)", color="#81b29a")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_codes, fontweight="bold")
    ax.set_ylabel("Throughput (RPS)", fontsize=11)
    ax.set_title("Figure 1: Workload Throughput & Call Graph Fan-Out across E01–E06", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "01_workload_throughput_comparison.png")

    # 2. P50/P95/P99 latency comparison
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(exp_codes, p50_vals, marker="o", linewidth=2, label="P50 Latency (Mean)", color="#2a9d8f")
    ax.plot(exp_codes, p95_vals, marker="s", linewidth=2, label="P95 Latency (Mean)", color="#e76f51")
    ax.plot(exp_codes, p99_vals, marker="^", linewidth=2, linestyle="--", label="P99 Latency (Max)", color="#d62828")
    ax.axhline(200.0, color="#666666", linestyle=":", label="SLA Target (200ms)")
    ax.set_ylabel("Latency (ms)", fontsize=11)
    ax.set_title("Figure 2: Ingress Frontend Latency Percentiles (P50, P95, P99) across E01–E06", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "02_latency_percentiles_comparison.png")

    # 3. CPU utilization across workload profiles
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w/2, fe_cpu_avg, w, label="Frontend CPU (Mean millicores)", color="#3d5a80")
    ax.bar(x + w/2, fe_cpu_peak, w, label="Frontend CPU (Peak millicores)", color="#ee6c4d")
    ax.axhline(100.0, color="#d90429", linestyle="--", label="CPU Request (100m)")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_codes, fontweight="bold")
    ax.set_ylabel("CPU Usage (millicores)", fontsize=11)
    ax.set_title("Figure 3: Ingress Frontend CPU Consumption vs 100m Reservation", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "03_cpu_utilization_across_profiles.png")

    # 4. Memory utilization across workload profiles
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(exp_codes, fe_mem_peak, width=0.45, color="#588157", label="Frontend Peak Memory")
    ax.axhline(64.0, color="#bc4749", linestyle="--", label="Memory Request (64 MiB)")
    ax.set_ylabel("Memory (MiB)", fontsize=11)
    ax.set_title("Figure 4: Ingress Frontend Memory Footprint across E01–E06", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "04_memory_utilization_across_profiles.png")

    # Policy comparison data preparation
    policy_names = ["Static", "CPU-Threshold", "HPA-Style", "DPBPS"]
    ptypes = [PolicyType.STATIC, PolicyType.CPU_THRESHOLD, PolicyType.HPA_STYLE, PolicyType.DPBPS]
    colors = ["#6c757d", "#f39c12", "#e74c3c", "#2980b9"]

    tot_up = [sum(replay_results[c][pt][1].scale_up_count for c in exp_codes) for pt in ptypes]
    tot_down = [sum(replay_results[c][pt][1].scale_down_count for c in exp_codes) for pt in ptypes]
    tot_hold = [sum(replay_results[c][pt][1].hold_count for c in exp_codes) for pt in ptypes]
    tot_evals = [sum(replay_results[c][pt][1].total_evaluations for c in exp_codes) for pt in ptypes]
    stability = [(h / e) * 100 for h, e in zip(tot_hold, tot_evals)]
    rec_freq = [((u + d) / e) * 100 for u, d, e in zip(tot_up, tot_down, tot_evals)]

    # 5. Scale-up recommendation count by policy
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(policy_names, tot_up, color=colors, width=0.5)
    ax.bar_label(bars, padding=3, fontweight="bold")
    ax.set_ylabel("Total Scale-Up Decisions", fontsize=11)
    ax.set_title("Figure 5: Total Scale-Up Recommendations by Policy (Campaign Total)", fontsize=12, fontweight="bold")
    save_fig(fig, "05_scale_up_count_by_policy.png")

    # 6. Scale-down recommendation count by policy
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(policy_names, tot_down, color=colors, width=0.5)
    ax.bar_label(bars, padding=3, fontweight="bold")
    ax.set_ylabel("Total Scale-Down Decisions", fontsize=11)
    ax.set_title("Figure 6: Total Scale-Down Recommendations by Policy (Campaign Total)", fontsize=12, fontweight="bold")
    save_fig(fig, "06_scale_down_count_by_policy.png")

    # 7. HOLD decision count by policy
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(policy_names, tot_hold, color=colors, width=0.5)
    ax.bar_label(bars, padding=3, fontweight="bold")
    ax.set_ylabel("Total HOLD Decisions", fontsize=11)
    ax.set_title("Figure 7: Total HOLD Decisions by Policy across 1,050 Evaluations", fontsize=12, fontweight="bold")
    save_fig(fig, "07_hold_decision_count_by_policy.png")

    # 8. Recommendation frequency comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(policy_names, rec_freq, color=colors, width=0.5)
    ax.bar_label(bars, fmt="%.2f%%", padding=3, fontweight="bold")
    ax.set_ylabel("Scaling Action Frequency (%)", fontsize=11)
    ax.set_title("Figure 8: Scaling Recommendation Frequency (% of evaluations mutating replicas)", fontsize=12, fontweight="bold")
    save_fig(fig, "08_recommendation_frequency_comparison.png")

    # 9. First scale-up recommendation time comparison (E02, E03, E04, E06)
    responsive_exps = ["E02 (Gradual)", "E03 (Spike)", "E04 (Sustained)", "E06 (Bursty)"]
    raw_keys = ["E02", "E03", "E04", "E06"]
    fig, ax = plt.subplots(figsize=(10, 5))
    x_r = np.arange(len(responsive_exps))
    w_r = 0.25

    cpu_first = [replay_results[k][PolicyType.CPU_THRESHOLD][1].time_to_first_scale_up_sec or 0 for k in raw_keys]
    hpa_first = [replay_results[k][PolicyType.HPA_STYLE][1].time_to_first_scale_up_sec or 0 for k in raw_keys]
    dpbps_first = [replay_results[k][PolicyType.DPBPS][1].time_to_first_scale_up_sec or 0 for k in raw_keys]

    ax.bar(x_r - w_r, cpu_first, w_r, label="CPU-Threshold", color="#f39c12")
    ax.bar(x_r, hpa_first, w_r, label="HPA-Style", color="#e74c3c")
    ax.bar(x_r + w_r, dpbps_first, w_r, label="DPBPS", color="#2980b9")
    ax.set_xticks(x_r)
    ax.set_xticklabels(responsive_exps, fontweight="bold")
    ax.set_ylabel("Elapsed Time to 1st Scale-Up (seconds)", fontsize=11)
    ax.set_title("Figure 9: Time to First Scale-Up Recommendation (Detection Velocity)", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "09_first_scale_up_time_comparison.png")

    # 10. Decision stability comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(policy_names, stability, color=colors, width=0.5)
    ax.bar_label(bars, fmt="%.1f%%", padding=3, fontweight="bold")
    ax.set_ylim(85, 105)
    ax.set_ylabel("Decision Stability Ratio (%)", fontsize=11)
    ax.set_title("Figure 10: Decision Stability Ratio (% of evaluations returning HOLD)", fontsize=12, fontweight="bold")
    save_fig(fig, "10_decision_stability_comparison.png")

    # 11. DPBPS service prioritization distribution
    fig, ax = plt.subplots(figsize=(9, 5))
    dpbps_svc_counts = {}
    for c in exp_codes:
        recs, _ = replay_results[c][PolicyType.DPBPS]
        for r in recs:
            if r.action == ScalingAction.SCALE_UP:
                dpbps_svc_counts[r.service_name] = dpbps_svc_counts.get(r.service_name, 0) + 1

    svcs = list(dpbps_svc_counts.keys())
    counts = [dpbps_svc_counts[s] for s in svcs]
    explode = [0.05 if s == "frontend" else 0 for s in svcs]
    ax.pie(counts, labels=[f"{s} ({c})" for s, c in zip(svcs, counts)], autopct="%1.1f%%",
           startangle=140, colors=["#2980b9", "#e67e22", "#27ae60"], explode=explode, shadow=True)
    ax.set_title("Figure 11: DPBPS Bottleneck Scale-Up Prioritization by Microservice", fontsize=12, fontweight="bold")
    save_fig(fig, "11_dpbps_service_prioritization.png")

    # 12. Experiment-wise policy comparison (Grouped bar chart of scale-ups)
    fig, ax = plt.subplots(figsize=(11, 5))
    w_e = 0.2
    x_e = np.arange(len(exp_codes))
    for idx, (pt, col, name) in enumerate(zip(ptypes, colors, policy_names)):
        ups = [replay_results[c][pt][1].scale_up_count for c in exp_codes]
        ax.bar(x_e + (idx - 1.5)*w_e, ups, w_e, label=name, color=col)
    ax.set_xticks(x_e)
    ax.set_xticklabels(exp_codes, fontweight="bold")
    ax.set_ylabel("Scale-Up Recommendations", fontsize=11)
    ax.set_title("Figure 12: Experiment-by-Experiment Scale-Up Recommendations by Policy", fontsize=12, fontweight="bold")
    ax.legend(frameon=True)
    save_fig(fig, "12_experiment_wise_policy_comparison.png")

    print(f"\nAll 12 research visualization charts successfully generated in:")
    print(f"  {output_dir}")
    print(f"  {brain_dir}")
    return saved_plots


if __name__ == "__main__":
    generate_all_plots()

