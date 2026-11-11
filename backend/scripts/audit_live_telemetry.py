import json
from datetime import datetime, timezone
from backend.scaling.kubernetes.telemetry_adapter import KubernetesTelemetryAdapter
from backend.scaling.kubernetes.prometheus_client import PrometheusClient

def main():
    print("=== LIVE PROMETHEUS AND KUBERNETES TELEMETRY AUDIT ===")
    
    with PrometheusClient(base_url="http://localhost:9090") as prom:
        adapter = KubernetesTelemetryAdapter(namespace="online-boutique", prometheus_client=prom)
        telemetry = adapter.collect_deployment_telemetry()
        print(f"Total deployments collected: {len(telemetry)}\n")
        
        target_services = [
            "frontend", "cartservice", "productcatalogservice", "currencyservice",
            "paymentservice", "shippingservice", "emailservice", "checkoutservice",
            "recommendationservice", "adservice"
        ]
        
        header = f"{'SERVICE':24} | {'REPLICAS':8} | {'CPU(m)':8} | {'CPU%':6} | {'MEM(Mi)':8} | {'MEM%':6} | {'RPS':6} | {'P95(ms)':7} | {'ERR':5} | {'STATUS':10}"
        print(header)
        print("-" * len(header))
        
        for t in telemetry:
            name = t.get("service_name", t.get("deployment_name"))
            if name not in target_services:
                continue
            cur_rep = t.get("desired_replicas")
            ready_rep = t.get("ready_replicas")
            cpu = t.get("cpu_usage_millicores")
            cpu_pct = t.get("cpu_utilization_percent")
            mem = t.get("memory_usage_mib")
            mem_pct = t.get("memory_utilization_percent")
            rps = t.get("request_rate")
            p95 = t.get("p95_latency_ms")
            err = t.get("error_rate")
            avail = t.get("telemetry_available")
            
            rep_str = f"{ready_rep}/{cur_rep}"
            cpu_str = f"{cpu:.1f}" if cpu is not None else "None"
            cpu_pct_str = f"{cpu_pct:.1f}%" if cpu_pct is not None else "None"
            mem_str = f"{mem:.1f}" if mem is not None else "None"
            mem_pct_str = f"{mem_pct:.1f}%" if mem_pct is not None else "None"
            rps_str = f"{rps:.2f}" if rps is not None else "None"
            p95_str = f"{p95:.1f}" if p95 is not None else "None"
            err_str = f"{err:.3f}" if err is not None else "None"
            stat_str = "COMPLETE" if avail else "INCOMPLETE"
            
            print(f"{name:24} | {rep_str:8} | {cpu_str:8} | {cpu_pct_str:6} | {mem_str:8} | {mem_pct_str:6} | {rps_str:6} | {p95_str:7} | {err_str:5} | {stat_str:10}")
            if t.get("missing_metrics"):
                print(f"   -> Missing: {t['missing_metrics']}")
            if t.get("diagnostics"):
                print(f"   -> Diag: {t['diagnostics']}")

if __name__ == "__main__":
    main()
