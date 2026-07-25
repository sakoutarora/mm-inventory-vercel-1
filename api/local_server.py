#!/usr/bin/env python3
"""Local development server — wraps lambda_handler with a plain HTTP server."""

import base64
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Load .env BEFORE importing lambda_function.
# config.py reads env vars at module level, so dotenv must be loaded first.
from dotenv import load_dotenv
load_dotenv()

from src.lambda_function import lambda_handler


class LambdaHandler(BaseHTTPRequestHandler):
    """Translates HTTP requests into API Gateway HTTP API v2 events."""

    def _handle(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Query string parameters
        qs = parse_qs(parsed.query, keep_blank_values=True)
        query_params = {k: v[-1] for k, v in qs.items()} if qs else None

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length else b""

        # Headers (lowercase keys, matching API Gateway)
        headers = {k.lower(): v for k, v in self.headers.items()}

        # Multipart: base64-encode body (matching API Gateway behavior)
        content_type = headers.get("content-type", "")
        is_base64 = False
        if "multipart/form-data" in content_type and body_bytes:
            body_str = base64.b64encode(body_bytes).decode("utf-8")
            is_base64 = True
        else:
            body_str = body_bytes.decode("utf-8") if body_bytes else None

        event = {
            "rawPath": path,
            "requestContext": {
                "http": {"method": self.command, "path": path},
            },
            "headers": headers,
            "queryStringParameters": query_params,
            "body": body_str,
            "isBase64Encoded": is_base64,
        }

        # Call the Lambda handler
        result = lambda_handler(event, None)

        # Write response
        status = result.get("statusCode", 200)
        self.send_response(status)
        for k, v in (result.get("headers") or {}).items():
            self.send_header(k, v)
        self.end_headers()

        body = result.get("body", "")
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    # Route all HTTP methods through _handle
    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_OPTIONS = _handle

    def log_message(self, format, *args):
        """Cleaner log output."""
        method = args[0].split()[0] if args else "?"
        path = args[0].split()[1] if args and len(args[0].split()) > 1 else "?"
        status = args[1] if len(args) > 1 else "?"
        print(f"  {method} {path} → {status}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), LambdaHandler)
    print(f"Local Lambda server running on http://localhost:{port}")
    print(f"Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
