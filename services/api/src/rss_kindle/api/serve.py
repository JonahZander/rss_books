from __future__ import annotations

import asyncio
import logging

import uvicorn

from rss_kindle.api.certs import ensure_self_signed
from rss_kindle.api.main import app
from rss_kindle.config import get_settings

logger = logging.getLogger(__name__)


async def _serve() -> None:
    """Run the app over plain HTTP and (optionally) HTTPS in one process.

    Both servers share the single `app` instance, so the lifespan's scheduler
    guard (`app.state.scheduler_task`) keeps the poller/scheduler running exactly
    once even though the lifespan executes per-server.
    """
    settings = get_settings()

    servers = [
        uvicorn.Server(
            uvicorn.Config(app, host="0.0.0.0", port=settings.http_port, log_level="info")
        )
    ]

    if settings.tls_enabled:
        san_ips = [ip for ip in settings.tls_san_ips.split(",") if ip.strip()]
        ensure_self_signed(settings.tls_cert_file, settings.tls_key_file, san_ips)
        servers.append(
            uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="0.0.0.0",
                    port=settings.https_port,
                    log_level="info",
                    ssl_certfile=str(settings.tls_cert_file),
                    ssl_keyfile=str(settings.tls_key_file),
                )
            )
        )
        logger.info(
            "serving HTTP on :%d and HTTPS on :%d",
            settings.http_port,
            settings.https_port,
        )
    else:
        logger.info("serving HTTP on :%d (TLS disabled)", settings.http_port)

    await asyncio.gather(*(s.serve() for s in servers))


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
