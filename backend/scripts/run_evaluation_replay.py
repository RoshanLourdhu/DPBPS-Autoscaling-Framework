"""
Executes full trace replay across all 6 experiments and prints structured comparative tables.
"""

import json
from backend.evaluation.replay_engine import TraceReplayEngine
from backend.evaluation.models import PolicyType

engine = TraceReplayEngine()
print("Starting Trace Replay across all 6 experiments...")
results = engine.replay_all_experiments()

print("\n" + "=" * 90)
print("TRACE REPLAY SUMMARY ACROSS EXPERIMENTS AND POLICIES")
print("=" * 90)

for exp_code, exp_results in results.items():
    print(f"\n--- EXPERIMENT {exp_code} ---")
    print(f"{'POLICY':<16} | {'EVALS':<5} | {'HOLD':<5} | {'UP':<4} | {'DOWN':<4} | {'1st UP (s)':<10} | {'MAX REP':<7} | {'STABILITY':<9}")
    print("-" * 75)
    for ptype, (recs, summ) in exp_results.items():
        stability = (summ.hold_count / summ.total_evaluations) * 100 if summ.total_evaluations > 0 else 0
        first_up = f"{summ.time_to_first_scale_up_sec:.1f}s" if summ.time_to_first_scale_up_sec is not None else "N/A"
        print(f"{ptype.value:<16} | {summ.total_evaluations:<5} | {summ.hold_count:<5} | {summ.scale_up_count:<4} | {summ.scale_down_count:<4} | {first_up:<10} | {summ.max_recommended_replicas:<7} | {stability:5.1f}%")

print("\n" + "=" * 90)
print("AGGREGATED TOTALS ACROSS ALL 6 EXPERIMENTS")
print("=" * 90)
totals = {pt: {"hold": 0, "up": 0, "down": 0, "total": 0} for pt in PolicyType}
for exp_code, exp_results in results.items():
    for ptype, (recs, summ) in exp_results.items():
        totals[ptype]["hold"] += summ.hold_count
        totals[ptype]["up"] += summ.scale_up_count
        totals[ptype]["down"] += summ.scale_down_count
        totals[ptype]["total"] += summ.total_evaluations

print(f"{'POLICY':<16} | {'TOTAL EVALS':<11} | {'TOTAL HOLD':<10} | {'TOTAL UP':<8} | {'TOTAL DOWN':<10} | {'OVERALL STABILITY':<17}")
print("-" * 85)
for pt, t in totals.items():
    stab = (t["hold"] / t["total"]) * 100 if t["total"] > 0 else 0
    print(f"{pt.value:<16} | {t['total']:<11} | {t['hold']:<10} | {t['up']:<8} | {t['down']:<10} | {stab:5.1f}%")

