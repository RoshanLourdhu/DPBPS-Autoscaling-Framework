"""
Prometheus query client for the DPBPS framework.

Provides a robust, production-conscious client for querying application-level
and infrastructure-level metrics from Prometheus.

Responsibilities:
- Connect to Prometheus HTTP API with configurable timeouts and error handling.
- Calculate request rates, P95 latencies (via histogram_quantile), and error rates.
- Retrieve container CPU usage and working set memory from Prometheus cAdvisor metrics.
- Explicitly distinguish between genuine zero measurements, stale samples, and missing telemetry.
- Enforce strict input validation on service names and namespaces to prevent query injection.
- Exclude internal health checks from business error rates.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

import backend.config as cfg


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# EXCEPTIONS
# ---------------------------------------------------------------------

class PrometheusClientError(Exception):
    """Base exception for all Prometheus client errors."""


class PrometheusConnectionError(PrometheusClientError):
    """Raised when connecting to Prometheus fails or times out."""


class PrometheusResponseError(PrometheusClientError):
    """Raised when Prometheus returns an HTTP error or error response status."""


class PrometheusDataError(PrometheusClientError):
    """Raised when Prometheus response JSON is malformed or has unexpected schema."""


# ---------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------

@dataclass
class MetricSample:
    """A single metric value with timestamp and associated labels."""
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    is_fresh: bool = True


@dataclass
class MetricQueryResult:
    """Result of an instant PromQL query execution."""
    query: str
    is_present: bool
    samples: List[MetricSample] = field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def first_value(self) -> Optional[float]:
        """Return the scalar value of the first sample if present, else None."""
        if self.is_present and self.samples:
            return self.samples[0].value
        return None

    @property
    def is_fresh(self) -> bool:
        """Return True if at least one sample is present and fresh."""
        return self.is_present and bool(self.samples) and all(s.is_fresh for s in self.samples)

    @property
    def latest_timestamp(self) -> Optional[datetime]:
        """Return the timestamp of the most recent sample if present."""
        if self.is_present and self.samples:
            return max(s.timestamp for s in self.samples)
        return None


@dataclass
class ServiceTelemetryResult:
    """
    Consolidated telemetry measurements for a single microservice.

    Distinguishes genuine zero values (e.g. 0.0 req/s under idle workload)
    from missing telemetry (None with an entry in missing_metrics).
    """
    service_name: str
    request_rate: Optional[float] = None
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    cpu_millicores: Optional[float] = None
    memory_mib: Optional[float] = None
    timestamp: Optional[datetime] = None
    is_complete: bool = False
    missing_metrics: List[str] = field(default_factory=list)
    diagnostic_messages: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------
# PROMETHEUS CLIENT
# ---------------------------------------------------------------------

class PrometheusClient:
    """
    Client for querying Prometheus HTTP API in Kubernetes environments.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_age_seconds: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        """
        Initialize the Prometheus client.

        Args:
            base_url: Base URL of Prometheus (default from cfg.PROMETHEUS_URL).
            timeout: HTTP request timeout in seconds (default from cfg.PROMETHEUS_TIMEOUT_SECONDS).
            max_age_seconds: Maximum age before a metric is considered stale.
            http_client: Optional httpx.Client instance (useful for mocking or custom transport).
        """
        self.base_url = (base_url or cfg.PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else cfg.PROMETHEUS_TIMEOUT_SECONDS
        self.max_age_seconds = max_age_seconds if max_age_seconds is not None else cfg.PROMETHEUS_MAX_AGE_SECONDS

        self._external_client = http_client is not None
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Accept": "application/json"}
        )

    def close(self) -> None:
        """Close the underlying HTTP client if internally created."""
        if not self._external_client and self._client:
            self._client.close()

    def __enter__(self) -> "PrometheusClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # INPUT VALIDATION
    # -----------------------------------------------------------------

    @staticmethod
    def _validate_identifier(value: str, field_name: str = "identifier") -> str:
        """
        Validate that an identifier contains only safe alphanumeric characters.
        Prevents PromQL label injection.
        """
        if not value or not isinstance(value, str):
            raise ValueError(f"{field_name} must be a non-empty string.")

        if not re.fullmatch(r"^[a-zA-Z0-9_\-\.]+$", value):
            raise ValueError(
                f"Invalid {field_name}: '{value}'. Must be alphanumeric with hyphens, underscores, or dots."
            )
        return value

    @staticmethod
    def _validate_window(value: str) -> str:
        """
        Validate a PromQL duration window (e.g., '30s', '1m', '5m').
        """
        if not value or not isinstance(value, str):
            raise ValueError("Time window must be a non-empty string.")

        if not re.fullmatch(r"^[0-9]+[smhd]$", value):
            raise ValueError(
                f"Invalid time window: '{value}'. Expected format like '30s', '1m', '5m', '1h'."
            )
        return value

    # -----------------------------------------------------------------
    # CORE HTTP QUERY EXECUTION
    # -----------------------------------------------------------------

    def execute_query(
        self,
        query: str,
        time_param: Optional[datetime] = None,
    ) -> MetricQueryResult:
        """
        Execute an instant PromQL query against the Prometheus /api/v1/query endpoint.

        Args:
            query: The PromQL query string.
            time_param: Optional evaluation timestamp (defaults to server now).

        Returns:
            MetricQueryResult containing parsed samples or missing/stale status.

        Raises:
            PrometheusConnectionError: On network failure or timeout.
            PrometheusResponseError: On HTTP 4xx/5xx or Prometheus status='error'.
            PrometheusDataError: On malformed response JSON.
        """
        params: Dict[str, Any] = {"query": query}
        if time_param is not None:
            params["time"] = time_param.timestamp()

        try:
            response = self._client.get("/api/v1/query", params=params)
        except httpx.TimeoutException as exc:
            logger.error("Prometheus query timed out after %s seconds: %s", self.timeout, query)
            raise PrometheusConnectionError(
                f"Prometheus query timed out after {self.timeout}s: {query}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Failed to connect to Prometheus at %s: %s", self.base_url, exc)
            raise PrometheusConnectionError(
                f"Failed to connect to Prometheus at {self.base_url}: {exc}"
            ) from exc

        if response.status_code != 200:
            logger.error("Prometheus HTTP error %s for query %s: %s", response.status_code, query, response.text)
            raise PrometheusResponseError(
                f"Prometheus HTTP {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            logger.error("Malformed JSON received from Prometheus for query %s", query)
            raise PrometheusDataError(
                f"Malformed JSON response from Prometheus: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise PrometheusDataError("Prometheus response root is not a dictionary.")

        status = payload.get("status")
        if status != "success":
            error_type = payload.get("errorType", "UnknownError")
            error_msg = payload.get("error", "No error message provided")
            logger.error("Prometheus API error (%s): %s", error_type, error_msg)
            raise PrometheusResponseError(
                f"Prometheus API error ({error_type}): {error_msg}"
            )

        data = payload.get("data", {})
        result_type = data.get("resultType")
        results = data.get("result", [])

        if not isinstance(results, list):
            raise PrometheusDataError(
                f"Expected list for 'result' field in Prometheus response, got {type(results).__name__}"
            )

        if not results:
            # Metric series does not exist or has no active data points in the evaluation window
            return MetricQueryResult(
                query=query,
                is_present=False,
                samples=[],
                error_message="No time series found matching the query."
            )

        now = datetime.now(timezone.utc)
        parsed_samples: List[MetricSample] = []

        for item in results:
            if not isinstance(item, dict):
                continue

            metric_labels = item.get("metric", {})
            value_pair = item.get("value")

            if not isinstance(value_pair, (list, tuple)) or len(value_pair) < 2:
                continue

            try:
                sample_epoch = float(value_pair[0])
                sample_dt = datetime.fromtimestamp(sample_epoch, tz=timezone.utc)
            except (ValueError, TypeError, OverflowError):
                continue

            try:
                raw_val = float(value_pair[1])
            except (ValueError, TypeError):
                continue

            # Check freshness
            age_seconds = (now - sample_dt).total_seconds()
            is_fresh = age_seconds <= self.max_age_seconds

            parsed_samples.append(
                MetricSample(
                    value=raw_val,
                    timestamp=sample_dt,
                    labels=metric_labels,
                    is_fresh=is_fresh,
                )
            )

        if not parsed_samples:
            return MetricQueryResult(
                query=query,
                is_present=False,
                samples=[],
                error_message="No valid metric samples could be parsed from the response."
            )

        return MetricQueryResult(
            query=query,
            is_present=True,
            samples=parsed_samples,
            error_message=None
        )

    # -----------------------------------------------------------------
    # DOMAIN-SPECIFIC APPLICATION METRIC QUERIES
    # -----------------------------------------------------------------

    def query_request_rate(
        self,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """
        Query the combined incoming request rate (requests/sec) for a microservice.

        Supports both HTTP services (frontend) and gRPC services (backend).
        Uses OTLP-exported metric series:
        - http_server_requests_total
        - rpc_server_requests_total
        """
        svc = self._validate_identifier(service_name, "service_name")
        win = self._validate_window(window)

        # Primary query: matches service_name or exported_job from OpenTelemetry
        query = (
            f"sum("
            f"  rate(http_server_requests_total{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_requests_total{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_requests_total{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_requests_total{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_request_duration_seconds_count{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_request_duration_seconds_count{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_call_duration_seconds_count{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_call_duration_seconds_count{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_duration_milliseconds_count{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_duration_milliseconds_count{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_milliseconds_count{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_milliseconds_count{{exported_job=\"{svc}\"}}[{win}])"
            f")"
        )
        return self.execute_query(query)

    def query_latency_quantile(
        self,
        quantile: float,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """
        Query an arbitrary percentile request latency in milliseconds.

        Calculates quantile using histogram_quantile(quantile, sum by (le) (rate(..._bucket[1m]))).
        Supports:
        - http_server_duration_milliseconds_bucket
        - rpc_server_duration_milliseconds_bucket
        - Fallback to duration_seconds_bucket (converted to ms).
        """
        if not (0.0 <= quantile <= 1.0):
            raise ValueError(f"Quantile must be between 0.0 and 1.0, got {quantile}")
        svc = self._validate_identifier(service_name, "service_name")
        win = self._validate_window(window)

        # Millisecond buckets query
        query_ms = (
            f"histogram_quantile({quantile:.2f}, sum by (le) ("
            f"  rate(http_server_duration_milliseconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_duration_milliseconds_bucket{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_milliseconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_milliseconds_bucket{{exported_job=\"{svc}\"}}[{win}])"
            f"))"
        )
        res_ms = self.execute_query(query_ms)
        if res_ms.is_present and res_ms.first_value is not None:
            # Ensure NaN or Inf values are handled safely
            val = res_ms.first_value
            if val >= 0 and not (val != val):  # not NaN
                return res_ms

        # Fallback query for seconds buckets (scaled by 1000 to ms)
        query_sec = (
            f"histogram_quantile({quantile:.2f}, sum by (le) ("
            f"  rate(http_server_duration_seconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_duration_seconds_bucket{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_seconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_duration_seconds_bucket{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_request_duration_seconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(http_server_request_duration_seconds_bucket{{exported_job=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_call_duration_seconds_bucket{{service_name=\"{svc}\"}}[{win}]) "
            f"  or rate(rpc_server_call_duration_seconds_bucket{{exported_job=\"{svc}\"}}[{win}])"
            f")) * 1000"
        )
        return self.execute_query(query_sec)

    def query_p50_latency(
        self,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """Query the 50th percentile (median) request latency in milliseconds."""
        return self.query_latency_quantile(0.50, service_name, window=window)

    def query_p95_latency(
        self,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """Query the 95th percentile request latency in milliseconds."""
        return self.query_latency_quantile(0.95, service_name, window=window)

    def query_p99_latency(
        self,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """Query the 99th percentile request latency in milliseconds."""
        return self.query_latency_quantile(0.99, service_name, window=window)

    def query_error_rate(
        self,
        service_name: str,
        window: str = "1m",
    ) -> MetricQueryResult:
        """
        Calculate the request error rate as a fraction between 0.0 and 1.0.

        Calculates:
        - HTTP: rate of 5xx responses divided by total HTTP request rate.
        - gRPC: rate of non-OK/non-0 status responses divided by total gRPC request rate.
        Excludes health check requests (rpc_service != 'grpc.health.v1.Health') to avoid
        skewing business error statistics.

        Returns:
            MetricQueryResult with 0.0 if traffic exists and error count is 0,
            or None if total request traffic is absent.
        """
        svc = self._validate_identifier(service_name, "service_name")
        win = self._validate_window(window)

        # First verify if there is any traffic
        rate_res = self.query_request_rate(service_name=svc, window=win)
        if not rate_res.is_present or rate_res.first_value is None:
            return MetricQueryResult(
                query="error_rate_calculation",
                is_present=False,
                samples=[],
                error_message="Total request rate telemetry is unavailable; error rate cannot be computed."
            )

        total_rate = rate_res.first_value
        if total_rate <= 0.0:
            # Genuine zero traffic -> error rate is 0.0
            return MetricQueryResult(
                query="error_rate_calculation",
                is_present=True,
                samples=[
                    MetricSample(
                        value=0.0,
                        timestamp=rate_res.latest_timestamp or datetime.now(timezone.utc),
                        is_fresh=rate_res.is_fresh,
                    )
                ]
            )

        # Error rate PromQL query (HTTP 5xx + gRPC non-zero status excluding health checks)
        error_rate_query = (
            f"("
            f"  sum("
            f"    rate(http_server_requests_total{{service_name=\"{svc}\",http_status_code=~\"5..\"}}[{win}]) "
            f"    or rate(http_server_requests_total{{exported_job=\"{svc}\",http_status_code=~\"5..\"}}[{win}]) "
            f"    or rate(rpc_server_requests_total{{service_name=\"{svc}\",rpc_grpc_status_code!~\"0|OK\",rpc_service!~\"(?i).*health.*\"}}[{win}]) "
            f"    or rate(rpc_server_requests_total{{exported_job=\"{svc}\",rpc_grpc_status_code!~\"0|OK\",rpc_service!~\"(?i).*health.*\"}}[{win}])"
            f"  ) or vector(0)"
            f") / {total_rate}"
        )
        res = self.execute_query(error_rate_query)
        if res.is_present and res.first_value is not None:
            # Clamp between 0.0 and 1.0
            clamped = max(0.0, min(1.0, res.first_value))
            res.samples[0].value = round(clamped, 4)
            return res

        # Default fallback if error rate query produced vector(0)
        return MetricQueryResult(
            query=error_rate_query,
            is_present=True,
            samples=[
                MetricSample(
                    value=0.0,
                    timestamp=rate_res.latest_timestamp or datetime.now(timezone.utc),
                    is_fresh=rate_res.is_fresh,
                )
            ]
        )

    # -----------------------------------------------------------------
    # CONTAINER RESOURCE METRIC QUERIES
    # -----------------------------------------------------------------

    def query_container_cpu(
        self,
        service_name: str,
        namespace: str = "online-boutique",
        window: str = "1m",
    ) -> MetricQueryResult:
        """
        Retrieve container CPU usage in millicores (1 core = 1000m) from Prometheus cAdvisor.

        Filters out pause/infrastructure containers (container != 'POD').
        """
        svc = self._validate_identifier(service_name, "service_name")
        ns = self._validate_identifier(namespace, "namespace")
        win = self._validate_window(window)

        query = (
            f"sum("
            f"  rate(container_cpu_usage_seconds_total{{"
            f"    namespace=\"{ns}\","
            f"    pod=~\"{svc}-.*|{svc}\","
            f"    container!=\"\","
            f"    container!=\"POD\""
            f"  }}[{win}])"
            f") * 1000"
        )
        return self.execute_query(query)

    def query_container_memory(
        self,
        service_name: str,
        namespace: str = "online-boutique",
    ) -> MetricQueryResult:
        """
        Retrieve container working-set memory in MiB from Prometheus cAdvisor.

        Preserves units: working-set bytes divided by (1024 * 1024).
        """
        svc = self._validate_identifier(service_name, "service_name")
        ns = self._validate_identifier(namespace, "namespace")

        query = (
            f"sum("
            f"  container_memory_working_set_bytes{{"
            f"    namespace=\"{ns}\","
            f"    pod=~\"{svc}-.*|{svc}\","
            f"    container!=\"\","
            f"    container!=\"POD\""
            f"  }}"
            f") / 1048576"
        )
        return self.execute_query(query)

    # -----------------------------------------------------------------
    # COMPREHENSIVE SERVICE TELEMETRY RETRIEVAL
    # -----------------------------------------------------------------

    def get_service_telemetry(
        self,
        service_name: str,
        namespace: str = "online-boutique",
        window: str = "1m",
    ) -> ServiceTelemetryResult:
        """
        Collect and validate all application and resource metrics for a service.

        Accurately flags missing or stale metrics without fabricating zeros.
        """
        svc = self._validate_identifier(service_name, "service_name")
        ns = self._validate_identifier(namespace, "namespace")
        win = self._validate_window(window)

        missing_metrics: List[str] = []
        diagnostics: List[str] = []

        # 1. Request rate
        try:
            req_res = self.query_request_rate(svc, window=win)
            if not req_res.is_present:
                request_rate = None
                missing_metrics.append("request_rate")
                diagnostics.append(f"Request rate missing: {req_res.error_message}")
            elif not req_res.is_fresh:
                request_rate = None
                missing_metrics.append("request_rate")
                diagnostics.append("Request rate is stale (exceeds max_age_seconds).")
            else:
                request_rate = max(0.0, req_res.first_value or 0.0)
        except Exception as exc:
            request_rate = None
            missing_metrics.append("request_rate")
            diagnostics.append(f"Error querying request rate: {exc}")

        # 2. Latency percentiles (P95 core; P50 & P99 extended)
        p50_latency: Optional[float] = None
        p99_latency: Optional[float] = None
        try:
            p95_res = self.query_p95_latency(svc, window=win)
            if not p95_res.is_present:
                p95_latency = None
                # If traffic is genuinely 0, latency is not considered missing, but inactive
                if request_rate == 0.0:
                    p95_latency = 0.0
                    p50_latency = 0.0
                    p99_latency = 0.0
                else:
                    missing_metrics.append("p95_latency")
                    diagnostics.append(f"P95 latency missing: {p95_res.error_message}")
            elif not p95_res.is_fresh:
                p95_latency = None
                missing_metrics.append("p95_latency")
                diagnostics.append("P95 latency is stale.")
            else:
                p95_latency = max(0.0, p95_res.first_value or 0.0)
                # Attempt P50 and P99
                try:
                    p50_res = self.query_p50_latency(svc, window=win)
                    if p50_res.is_present and p50_res.first_value is not None:
                        p50_latency = max(0.0, p50_res.first_value)
                except Exception:
                    p50_latency = None
                try:
                    p99_res = self.query_p99_latency(svc, window=win)
                    if p99_res.is_present and p99_res.first_value is not None:
                        p99_latency = max(0.0, p99_res.first_value)
                except Exception:
                    p99_latency = None
        except Exception as exc:
            p95_latency = None
            missing_metrics.append("p95_latency")
            diagnostics.append(f"Error querying P95 latency: {exc}")

        # 3. Error rate
        try:
            err_res = self.query_error_rate(svc, window=win)
            if not err_res.is_present:
                error_rate = None
                missing_metrics.append("error_rate")
                diagnostics.append(f"Error rate missing: {err_res.error_message}")
            elif not err_res.is_fresh:
                error_rate = None
                missing_metrics.append("error_rate")
                diagnostics.append("Error rate is stale.")
            else:
                error_rate = max(0.0, min(1.0, err_res.first_value or 0.0))
        except Exception as exc:
            error_rate = None
            missing_metrics.append("error_rate")
            diagnostics.append(f"Error querying error rate: {exc}")

        # 4. CPU usage (millicores)
        try:
            cpu_res = self.query_container_cpu(svc, namespace=ns, window=win)
            if not cpu_res.is_present or not cpu_res.is_fresh:
                cpu_millicores = None
                missing_metrics.append("cpu_usage")
                diagnostics.append("CPU usage telemetry missing or stale.")
            else:
                cpu_millicores = round(cpu_res.first_value or 0.0, 2)
        except Exception as exc:
            cpu_millicores = None
            missing_metrics.append("cpu_usage")
            diagnostics.append(f"Error querying CPU usage: {exc}")

        # 5. Memory usage (MiB)
        try:
            mem_res = self.query_container_memory(svc, namespace=ns)
            if not mem_res.is_present or not mem_res.is_fresh:
                memory_mib = None
                missing_metrics.append("memory_usage")
                diagnostics.append("Memory usage telemetry missing or stale.")
            else:
                memory_mib = round(mem_res.first_value or 0.0, 2)
        except Exception as exc:
            memory_mib = None
            missing_metrics.append("memory_usage")
            diagnostics.append(f"Error querying memory usage: {exc}")

        is_complete = len(missing_metrics) == 0

        return ServiceTelemetryResult(
            service_name=svc,
            request_rate=request_rate,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            error_rate=error_rate,
            cpu_millicores=cpu_millicores,
            memory_mib=memory_mib,
            timestamp=datetime.now(timezone.utc),
            is_complete=is_complete,
            missing_metrics=missing_metrics,
            diagnostic_messages=diagnostics,
        )

