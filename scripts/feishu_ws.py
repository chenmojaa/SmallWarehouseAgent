"""
Feishu / Lark long-connection (WebSocket) client.

Usage:
    set FEISHU_APP_ID=cli_xxx
    set FEISHU_APP_SECRET=xxx
    python scripts/feishu_ws.py

Environment variables:
    FEISHU_APP_ID      Lark application App ID
    FEISHU_APP_SECRET  Lark application App Secret

Note:
    The script blocks on `client.start()` and must keep running so the
    WebSocket connection stays alive. On success the SDK logs
    `[Lark] ... connected to <ws url>` (this is the lark-oapi equivalent
    of "ws client ready").
"""
import logging
import os
import sys

import lark_oapi as lark

APP_ID = os.environ.get("FEISHU_APP_ID", "YOUR_FEISHU_APP_ID")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "YOUR_FEISHU_APP_SECRET")


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def main() -> None:
    _configure_logging()
    logging.info("Building Lark WS long-connection client (app_id=%s)", APP_ID)

    # No event handler here: we only need to verify the long connection
    # is reachable from the open platform. Pass a real handler (built via
    # EventDispatcherHandler.builder(<encrypt_key>, <verification_token>))
    # once you start handling real events.
    client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=None,
        log_level=lark.LogLevel.INFO,
    )

    logging.info(
        "Starting Feishu long-connection client; press Ctrl+C to stop. "
        "Watch for 'connected to' in the log."
    )
    client.start()


if __name__ == "__main__":
    main()
