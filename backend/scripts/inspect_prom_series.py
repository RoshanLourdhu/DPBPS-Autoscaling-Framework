import urllib.request
import urllib.parse
import json

def run_query(query):
    url = f"http://localhost:9090/api/v1/query?query={urllib.parse.quote(query)}"
    res = urllib.request.urlopen(url)
    data = json.loads(res.read())['data']['result']
    print(f"\nQUERY: {query}")
    print(f"RESULTS: {len(data)}")
    for s in data:
        print("  Metric:", s['metric'])
        print("  Value:", s['value'])

def main():
    queries = [
        'sum(rate(http_server_request_duration_seconds_count{service_name="frontend"}[1m]))',
        'sum(rate(rpc_server_call_duration_seconds_count{service_name="checkoutservice"}[1m]))',
        'sum(rate(rpc_server_call_duration_seconds_count{service_name="productcatalogservice"}[1m]))',
        'sum by (service_name) (http_server_request_duration_seconds_count)',
        'sum by (service_name) (rpc_server_call_duration_seconds_count)',
    ]
    for q in queries:
        run_query(q)

if __name__ == "__main__":
    main()
