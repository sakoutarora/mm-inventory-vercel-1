import base64
import io
from multipart.multipart import parse_options_header
from multipart.multipart import MultipartParser, QuerystringParser


def parse_multipart_event(event: dict) -> dict[str, bytes]:
    """Parse a multipart/form-data request from API Gateway event.

    API Gateway sends the body as base64 when isBase64Encoded=true.
    Returns a dict mapping field names to their raw bytes.
    """
    content_type = ""
    headers = event.get("headers") or {}
    # Headers may be case-insensitive
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = v
            break

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    # Extract boundary from content-type
    _, params = parse_options_header(content_type)
    boundary = params.get(b"boundary", b"")
    if isinstance(boundary, str):
        boundary = boundary.encode("utf-8")

    if not boundary:
        return {}

    # Simple boundary-based parser
    files = {}
    parts = body_bytes.split(b"--" + boundary)

    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue

        # Split headers from body
        if b"\r\n\r\n" in part:
            header_section, file_data = part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in part:
            header_section, file_data = part.split(b"\n\n", 1)
        else:
            continue

        # Remove trailing boundary marker
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]
        if file_data.endswith(b"--"):
            file_data = file_data[:-2]
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]

        # Extract field name from Content-Disposition
        header_str = header_section.decode("utf-8", errors="replace")
        name = None
        for line in header_str.split("\n"):
            line = line.strip()
            if line.lower().startswith("content-disposition"):
                for param in line.split(";"):
                    param = param.strip()
                    if param.startswith("name="):
                        name = param.split("=", 1)[1].strip('"')
                        break

        if name:
            files[name] = file_data

    return files
