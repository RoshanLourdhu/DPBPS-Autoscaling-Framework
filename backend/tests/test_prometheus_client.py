"""
Automated unit tests for DPBPS PrometheusClient.

Verifies:
1. Successful Prometheus query parsing.
2. Prometheus API error response handling.
3. Connection timeout handling.
4. Connection failure handling.
5. Malformed JSON response handling.
6. Missing metric handling (empty series).
7. Genuine zero-valued metric handling (distinguished from missing data).
8. Request-rate query generation and parsing.
9. P95 histogram latency query generation and parsing.
10. Error-rate query generation and calculation.
11. Container CPU query generation and millicore conversion.
12. Container memory query generation and MiB conversion.
13. Input validation against label injection on service and namespace.
14. Stale telemetry detection against max_age_seconds.
15. Consolidated get_service_telemetry handling of mixed present/missing metrics.
"""

import time
from datetime import datetime, timezone
import pytest
import httpx

from backend.scaling.kubernetes.prometheus_client import (
    PrometheusClient,
    PrometheusConnectionError,
    PrometheusResponseError,
    PrometheusDataError,
    MetricQueryResult,
    ServiceTelemetryResult,
)


# ---------------------------------------------------------------------
# FIXTURES AND HELPERS
# ---------------------------------------------------------------------

def make_prom_vector_response(val: float, timestamp: float = None, metric_labels: dict = None) -> dict:
    """Generate a standard Prometheus instant query JSON payload."""
    ts = timestamp if timestamp is not None else time.time()
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": metric_labels or {"service_name": "frontend"},
                    "value": [ts, str(val)]
                }
            ]
        }
    }


def make_mock_client(response_payload: dict, status_code: int = 200) -> PrometheusClient:
    """Create a PrometheusClient with an httpx.MockTransport returning the given payload."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=response_payload)

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    return PrometheusClient(http_client=http_client, max_age_seconds=60.0)


# ---------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------

def test_successful_query():
    """1. Test successful Prometheus query parsing."""
    now = time.time()
    payload = make_prom_vector_response(42.5, timestamp=now)
    client = make_mock_client(payload)

    result = client.execute_query("up")
    assert result.is_present is True
    assert result.is_fresh is True
    assert result.first_value == 42.5
    assert len(result.samples) == 1
    assert result.samples[0].value == 42.5
    assert result.error_message is None


def test_api_error_response():
    """2. Test Prometheus API error response (status != 'success')."""
    payload = {
        "status": "error",
        "errorType": "bad_data",
        "error": "parse error: unexpected identifier"
    }
    client = make_mock_client(payload, status_code=400)

    with pytest.raises(PrometheusResponseError) as exc_info:
        client.execute_query("bad query syntax")
    assert "Prometheus HTTP 400" in str(exc_info.value)


def test_api_status_error_with_200():
    """Test Prometheus status='error' with HTTP 200."""
    payload = {
        "status": "error",
        "errorType": "execution",
        "error": "query execution failed"
    }
    client = make_mock_client(payload, status_code=200)

    with pytest.raises(PrometheusResponseError) as exc_info:
        client.execute_query("failing_query")
    assert "Prometheus API error (execution)" in str(exc_info.value)


def test_connection_timeout():
    """3. Test connection timeout handling."""
    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("Connection timed out", request=request)

    mock_transport = httpx.MockTransport(timeout_handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client, timeout=2.0)

    with pytest.raises(PrometheusConnectionError) as exc_info:
        client.execute_query("up")
    assert "timed out after 2.0s" in str(exc_info.value)


def test_connection_failure():
    """4. Test connection failure handling."""
    def connect_error_handler(request: httpx.Request):
        raise httpx.ConnectError("Failed to establish connection", request=request)

    mock_transport = httpx.MockTransport(connect_error_handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    with pytest.raises(PrometheusConnectionError) as exc_info:
        client.execute_query("up")
    assert "Failed to connect to Prometheus" in str(exc_info.value)


def test_malformed_json():
    """5. Test malformed JSON response handling."""
    def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=b"invalid json response")

    mock_transport = httpx.MockTransport(malformed_handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    with pytest.raises(PrometheusDataError) as exc_info:
        client.execute_query("up")
    assert "Malformed JSON response" in str(exc_info.value)


def test_missing_metric_empty_result():
    """6. Test missing metric when Prometheus returns an empty result list."""
    payload = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": []
        }
    }
    client = make_mock_client(payload)

    result = client.execute_query("absent_metric_total")
    assert result.is_present is False
    assert result.first_value is None
    assert len(result.samples) == 0
    assert "No time series found" in result.error_message


def test_genuine_zero_measurement():
    """7. Test genuine zero-valued metric is distinguished from missing telemetry."""
    now = time.time()
    payload = make_prom_vector_response(0.0, timestamp=now)
    client = make_mock_client(payload)

    result = client.execute_query("rate(http_server_requests_total[1m])")
    assert result.is_present is True
    assert result.first_value == 0.0
    assert result.is_fresh is True
    # Zero is not None!
    assert result.first_value is not None


def test_request_rate_query_generation():
    """8. Test request-rate query generation."""
    last_query = {}

    def capture_handler(request: httpx.Request) -> httpx.Response:
        last_query["url"] = str(request.url)
        last_query["query"] = request.url.params.get("query")
        return httpx.Response(status_code=200, json=make_prom_vector_response(120.5))

    mock_transport = httpx.MockTransport(capture_handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_request_rate(service_name="checkoutservice", window="2m")
    assert res.is_present is True
    assert res.first_value == 120.5
    assert "checkoutservice" in last_query["query"]
    assert "[2m]" in last_query["query"]
    assert "http_server_requests_total" in last_query["query"]
    assert "rpc_server_requests_total" in last_query["query"]


def test_p95_latency_query_generation():
    """9. Test P95 histogram latency query generation."""
    captured_queries = []

    def capture_handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query")
        captured_queries.append(q)
        return httpx.Response(status_code=200, json=make_prom_vector_response(85.4))

    mock_transport = httpx.MockTransport(capture_handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_p95_latency(service_name="cartservice", window="1m")
    assert res.is_present is True
    assert res.first_value == 85.4
    assert any("histogram_quantile(0.95" in q for q in captured_queries)
    assert any("cartservice" in q for q in captured_queries)
    assert any("sum by (le)" in q for q in captured_queries)


def test_error_rate_query_generation():
    """10. Test error-rate calculation."""
    # When request rate is 100 req/s, and error rate query returns 0.05 (5%)
    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query")
        if "5.." in q or "rpc_grpc_status_code" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(0.05))
        # Total request rate query
        return httpx.Response(status_code=200, json=make_prom_vector_response(100.0))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_error_rate(service_name="frontend", window="1m")
    assert res.is_present is True
    assert res.first_value == 0.05


def test_error_rate_when_traffic_is_zero():
    """Test error-rate calculation when traffic is genuine zero."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=make_prom_vector_response(0.0))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_error_rate(service_name="frontend", window="1m")
    assert res.is_present is True
    # Zero traffic must give 0.0 error rate
    assert res.first_value == 0.0


def test_error_rate_when_traffic_telemetry_missing():
    """Test error-rate calculation when traffic telemetry is completely missing."""
    empty_payload = {"status": "success", "data": {"resultType": "vector", "result": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=empty_payload)

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_error_rate(service_name="frontend", window="1m")
    assert res.is_present is False
    assert res.first_value is None


def test_container_cpu_query():
    """11. Test container CPU usage in millicores."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.params.get("query")
        # 0.15 cores = 150 millicores (Prometheus query multiplies by 1000)
        return httpx.Response(status_code=200, json=make_prom_vector_response(150.0))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_container_cpu("productcatalogservice", namespace="online-boutique")
    assert res.is_present is True
    assert res.first_value == 150.0
    assert "container_cpu_usage_seconds_total" in captured["query"]
    assert 'container!="POD"' in captured["query"]
    assert 'namespace="online-boutique"' in captured["query"]


def test_container_memory_query():
    """12. Test container memory usage in MiB."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.params.get("query")
        # 64 MiB
        return httpx.Response(status_code=200, json=make_prom_vector_response(64.0))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res = client.query_container_memory("shippingservice", namespace="online-boutique")
    assert res.is_present is True
    assert res.first_value == 64.0
    assert "container_memory_working_set_bytes" in captured["query"]
    assert "/ 1048576" in captured["query"]


def test_input_validation_safety():
    """13. Test input validation against PromQL injection attacks."""
    client = PrometheusClient(http_client=httpx.Client(base_url="http://mock:9090"))

    # Invalid service names
    with pytest.raises(ValueError):
        client.query_request_rate('frontend"; DROP TABLE users; --')

    with pytest.raises(ValueError):
        client.query_request_rate('frontend{service="bad"}')

    with pytest.raises(ValueError):
        client.query_request_rate('')

    # Invalid time windows
    with pytest.raises(ValueError):
        client.query_request_rate('frontend', window='1m; delete')

    with pytest.raises(ValueError):
        client.query_request_rate('frontend', window='invalid')


def test_stale_telemetry_handling():
    """14. Test stale telemetry detection."""
    # Sample timestamp 120 seconds in the past, with max_age_seconds = 60
    stale_timestamp = time.time() - 120.0
    payload = make_prom_vector_response(50.0, timestamp=stale_timestamp)
    client = make_mock_client(payload)
    client.max_age_seconds = 60.0

    res = client.execute_query("up")
    assert res.is_present is True
    assert res.is_fresh is False


def test_get_service_telemetry_complete():
    """15. Test consolidated get_service_telemetry when all metrics are present and fresh."""
    now = time.time()

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query")
        if "http_server_requests_total" in q and "5.." in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(0.01, now))
        elif "http_server_requests_total" in q or "rpc_server_requests_total" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(300.0, now))
        elif "histogram_quantile" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(45.2, now))
        elif "container_cpu_usage" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(210.0, now))
        elif "container_memory_working_set" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(128.5, now))
        return httpx.Response(status_code=200, json=make_prom_vector_response(1.0, now))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    telemetry = client.get_service_telemetry("frontend", namespace="online-boutique")
    assert telemetry.service_name == "frontend"
    assert telemetry.request_rate == 300.0
    assert telemetry.p95_latency_ms == 45.2
    assert telemetry.error_rate == 0.01
    assert telemetry.cpu_millicores == 210.0
    assert telemetry.memory_mib == 128.5
    assert telemetry.is_complete is True
    assert len(telemetry.missing_metrics) == 0


def test_get_service_telemetry_partial_missing():
    """Test get_service_telemetry when application telemetry is missing but resource telemetry is present."""
    now = time.time()
    empty_payload = {"status": "success", "data": {"resultType": "vector", "result": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query")
        if "container_cpu_usage" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(50.0, now))
        elif "container_memory_working_set" in q:
            return httpx.Response(status_code=200, json=make_prom_vector_response(64.0, now))
        # Application metrics are not yet instrumented -> return empty
        return httpx.Response(status_code=200, json=empty_payload)

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    telemetry = client.get_service_telemetry("paymentservice", namespace="online-boutique")
    assert telemetry.service_name == "paymentservice"
    assert telemetry.request_rate is None
    assert telemetry.p95_latency_ms is None
    assert telemetry.error_rate is None
    assert telemetry.cpu_millicores == 50.0
    assert telemetry.memory_mib == 64.0
    assert telemetry.is_complete is False
    assert "request_rate" in telemetry.missing_metrics
    assert "p95_latency" in telemetry.missing_metrics
    assert "error_rate" in telemetry.missing_metrics
    assert "cpu_usage" not in telemetry.missing_metrics
    assert "memory_usage" not in telemetry.missing_metrics


def test_p50_and_p99_latency_query_generation():
    """Test P50 and P99 quantile query generation."""
    captured_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.url.params.get("query"))
        now = time.time()
        return httpx.Response(status_code=200, json=make_prom_vector_response(25.0, now))

    mock_transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=mock_transport, base_url="http://mock-prometheus:9090")
    client = PrometheusClient(http_client=http_client)

    res_p50 = client.query_p50_latency("frontend", window="1m")
    assert res_p50.is_present is True
    assert res_p50.first_value == 25.0
    assert any("histogram_quantile(0.50" in q for q in captured_queries)

    res_p99 = client.query_p99_latency("frontend", window="2m")
    assert res_p99.is_present is True
    assert res_p99.first_value == 25.0
    assert any("histogram_quantile(0.99" in q for q in captured_queries)
    assert any("[2m]" in q for q in captured_queries)


def test_latency_quantile_invalid_bounds():
    """Test quantile validation rejects out-of-range bounds."""
    client = PrometheusClient()
    with pytest.raises(ValueError, match="Quantile must be between 0.0 and 1.0"):
        client.query_latency_quantile(-0.1, "frontend")
    with pytest.raises(ValueError, match="Quantile must be between 0.0 and 1.0"):
        client.query_latency_quantile(1.5, "frontend")


