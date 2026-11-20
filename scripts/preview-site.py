#!/usr/bin/env python3
"""Serve only the public site using Portmanager's claimed preview port."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path


def main() -> None:
    try:
        port = int(os.environ["PM_PORT_SITE"])
        host = os.environ["PM_HOST"]
    except (KeyError, ValueError) as error:
        raise SystemExit("Start with: portmanager run . -- python3 scripts/preview-site.py") from error
    if host != "127.0.0.1":
        raise SystemExit("The site preview must bind to 127.0.0.1.")
    root = Path(__file__).resolve().parent.parent / "site"
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    with ThreadingHTTPServer((host, port), handler) as server:
        print(f"Site preview: {os.environ['PM_URL_SITE']}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
