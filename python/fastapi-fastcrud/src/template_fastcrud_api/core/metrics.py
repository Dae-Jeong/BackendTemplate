from dataclasses import dataclass
from http import HTTPMethod

from prometheus_client import CollectorRegistry, Counter, Histogram

from template_fastcrud_api.core.contracts import HttpRequestResult


@dataclass
class HttpMetrics:
    registry: CollectorRegistry
    requests: Counter
    duration: Histogram
    failed: bool = False

    def record(self, result: HttpRequestResult) -> None:
        """Prometheus 라벨 변환과 기록 실패 격리를 이 경계에서 처리합니다."""
        try:
            labels = {
                "method": result.method if result.method in HTTPMethod else "OTHER",
                "route": result.route,
                "status": str(result.status) if result.status is not None else "none",
                "completion": result.completion.value,
                "execution": result.execution.value,
            }
            self.requests.labels(**labels).inc()
            self.duration.labels(**labels).observe(result.duration_seconds)
        except Exception:
            # 누락된 계측을 정상으로 공개하지 않고 원래 응답·예외를 유지합니다.
            self.failed = True


def create_metrics() -> HttpMetrics:
    registry = CollectorRegistry()
    labels = ("method", "route", "status", "completion", "execution")
    return HttpMetrics(
        registry=registry,
        requests=Counter(
            "http_requests_total",
            "HTTP requests by observed outcome.",
            labels,
            registry=registry,
        ),
        duration=Histogram(
            "http_request_duration_seconds",
            "Time to final response body send, or incomplete execution exit.",
            labels,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=registry,
        ),
    )
