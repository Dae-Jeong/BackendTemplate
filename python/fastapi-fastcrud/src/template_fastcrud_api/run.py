import sys

import uvicorn
from pydantic import ValidationError

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.contracts import LogContext
from template_fastcrud_api.core.logging import configure_logging
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.http.observation import HttpObservation


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        # 환경값과 알 수 없는 키 이름은 출력하지 않습니다.
        for detail in error.errors(include_input=False, include_context=False):
            field = detail["loc"][0] if detail["loc"] else "settings"
            if field not in Settings.model_fields:
                field = "settings"
            print(f"{field}: {detail['type']}", file=sys.stderr)
        raise SystemExit(1) from None

    configure_logging(
        LogContext(
            settings.app_name, settings.service_version, settings.app_environment
        ),
        settings.log_level,
        http_boundary=HttpObservation.__call__.__code__,
    )
    app = create_app(settings)
    uvicorn.run(
        HttpObservation(app, app.state.metrics, log_context=app.state.log_context),
        host=settings.server_host,
        port=settings.server_port,
        log_level=settings.log_level,
        access_log=False,
        log_config=None,
        workers=1,
        timeout_graceful_shutdown=settings.shutdown_timeout_seconds,
    )


if __name__ == "__main__":
    main()
