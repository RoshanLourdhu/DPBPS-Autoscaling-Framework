import json

p = r'D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments\exp_20261110T173312_bursty_traffic_55733a14\telemetry_metrics.json'
with open(p) as f:
    tm = json.load(f)

print('INDEX | ELAPSED | STAGE | FE_RPS | FE_P95 | FE_CPU | PROD_RPS | CART_RPS')
for i, s in enumerate(tm['snapshots']):
    t = s.get('elapsed_seconds', i*10)
    st = s.get('stage', 'N/A')
    fe = s['services']['frontend']
    prod = s['services']['productcatalogservice']
    cart = s['services']['cartservice']
    fe_r = fe.get('request_rate', 0.0) or 0.0
    fe_p = fe.get('p95_latency_ms', 0.0) or 0.0
    fe_c = fe.get('cpu_usage_millicores', 0.0) or 0.0
    pr_r = prod.get('request_rate', 0.0) or 0.0
    ca_r = cart.get('request_rate', 0.0) or 0.0
    print(f"{i:5d} | {t:6.1f}s | {st:20s} | {fe_r:6.2f} | {fe_p:7.1f}ms | {fe_c:5.1f}m | {pr_r:8.2f} | {ca_r:6.2f}")

