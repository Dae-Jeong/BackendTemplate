from typing import cast

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from template_fastcrud_api.core.metrics import HttpMetrics

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    response_class=Response,
    responses={
        200: {"content": {"text/plain": {}}},
        503: {"description": "Metrics unavailable"},
    },
)
def metrics(request: Request) -> Response:
    state = cast(HttpMetrics, request.app.state.metrics)
    if state.failed:
        return Response(
            "Metrics unavailable\n", status_code=503, media_type="text/plain"
        )
    try:
        return Response(
            generate_latest(state.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
    except Exception:
        state.failed = True
        return Response(
            "Metrics unavailable\n", status_code=503, media_type="text/plain"
        )
