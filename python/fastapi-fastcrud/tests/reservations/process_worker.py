"""Isolated process/crash fixture. Never target a service database."""

import asyncio
import json
import os
import sys
from dataclasses import asdict

from sqlalchemy import event

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.clock import system_clock
from template_fastcrud_api.core.database import primary_session
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.exceptions.reservations import SoldOut
from template_fastcrud_api.services.reservations import reserve


async def run(url: str, key: str, mode: str) -> None:
    app = create_app(Settings(db_primary_url=url))
    async with app.router.lifespan_context(app):
        async with primary_session(
            app.state.primary_session_factory, app.state.database_metrics
        ) as session:
            print("ready", flush=True)
            sys.stdin.readline()
            if mode in ("before_commit", "after_commit"):

                def crash(sync_session):
                    os._exit(23 if mode == "before_commit" else 24)

                event.listen(session.sync_session, mode, crash)
            try:
                result = await reserve(
                    session=session,
                    metrics=app.state.database_metrics,
                    product_id="demo",
                    key=key,
                    clock=system_clock,
                )
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "replayed": result.replayed,
                            "reservation": asdict(result.reservation),
                        },
                        default=str,
                    ),
                    flush=True,
                )
            except SoldOut:
                print(json.dumps({"status": "sold_out"}), flush=True)


if __name__ == "__main__":
    asyncio.run(run(*sys.argv[1:]))
