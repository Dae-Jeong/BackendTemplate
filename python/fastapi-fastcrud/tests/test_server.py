import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

SERVER = """
import asyncio
import sys
import uvicorn
from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.core.contracts import LogContext
from template_fastcrud_api.core.logging import configure_logging
from template_fastcrud_api.http.observation import HttpObservation

async def prepare(app, stack):
    async def close():
        print(f"RESOURCE_CLOSED ready={app.state.ready}", flush=True)
    stack.push_async_callback(close)

settings = Settings()
context = LogContext(settings.app_name, settings.service_version, settings.app_environment)
configure_logging(context, settings.log_level, http_boundary=HttpObservation.__call__.__code__)
configure_logging(context, settings.log_level, http_boundary=HttpObservation.__call__.__code__)
app = create_app(settings, prepare=prepare)

@app.get('/test/error')
async def fail():
    raise ValueError('private-exception-marker')

@app.get('/test/drain')
async def drain():
    print('REQUEST_STARTED', flush=True)
    await asyncio.to_thread(sys.stdin.readline)
    return {'finished': True}

uvicorn.run(HttpObservation(app, app.state.metrics, log_context=context),
            fd=int(sys.argv[1]), access_log=False, log_config=None,
            timeout_graceful_shutdown=settings.shutdown_timeout_seconds)
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX SIGTERM·상속 socket 시험입니다.")
def test_sigterm_drains_request_before_resource_cleanup() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-c", SERVER, str(listener.fileno())],
            pass_fds=(listener.fileno(),),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        assert process.stdin is not None
        lines: queue.Queue[str] = queue.Queue()
        captured: list[str] = []

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                captured.append(line)
                lines.put(line)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        def wait_for(message: str) -> None:
            while True:
                line = lines.get(timeout=10)
                if message in line:
                    return

        def request(path: str) -> bytes:
            with urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
                assert response.status == 200
                return response.read()

        try:
            wait_for("server.listening")
            assert request("/health/ready") == b'{"status":"ready"}'
            with pytest.raises(HTTPError) as caught:
                request("/test/error?token=private-query-marker")
            assert caught.value.code == 500
            caught.value.close()
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(request, "/test/drain")
                try:
                    wait_for("REQUEST_STARTED")
                    process.send_signal(signal.SIGTERM)
                    wait_for("server.stopping")
                finally:
                    process.stdin.write("finish\n")
                    process.stdin.flush()
                assert pending.result(timeout=10) == b'{"finished":true}'
            wait_for("RESOURCE_CLOSED ready=False")
            process.wait(timeout=10)
            assert process.returncode in (0, -signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            reader.join(timeout=5)
            process.stdout.close()
        records = [
            json.loads(line)
            for line in captured
            if not line.startswith(("REQUEST_STARTED", "RESOURCE_CLOSED"))
        ]
        assert "private-" not in "".join(captured)
        failures = [r for r in records if r["event"]["action"] == "http.failed"]
        summaries = [r for r in records if r["event"]["action"] == "http.completed"]
        assert len(failures) == 1
        assert len(summaries) == 2
        assert failures[0]["app"]["work"]["id"] == summaries[0]["app"]["work"]["id"]
        assert len([r for r in records if "error" in r]) == 1
