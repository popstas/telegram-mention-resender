"""Tiny stdlib HTTP server for manually testing target_webhook delivery.

Run it locally and point an instance's ``target_webhook.url`` at
``http://localhost:8002/`` (or any path). Each incoming request is printed
to stdout and the server responds with ``200 OK`` and a short JSON ack.

Usage:
    python scripts/test_webhook_server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8002


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "TelegramWebhookTester/1.0"

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) if length > 0 else b""
        try:
            decoded = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            decoded = repr(raw_body)

        print(f"--- {self.command} {self.path} ---", flush=True)
        for header, value in self.headers.items():
            print(f"{header}: {value}", flush=True)
        print("", flush=True)
        print(decoded, flush=True)
        print("--- end ---", flush=True)

        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        body = json.dumps({"ok": True, "hint": "POST to this URL"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


def build_server(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> ThreadingHTTPServer:
    """Return a configured but not-yet-serving HTTP server."""
    return ThreadingHTTPServer((host, port), WebhookHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    server = build_server(args.host, args.port)
    print(f"Listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
