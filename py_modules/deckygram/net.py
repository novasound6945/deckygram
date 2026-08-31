"""Shared HTTP plumbing: TLS context and multipart uploads.

Stdlib only.  Both destinations (Telegram, Discord) upload files the same
way - a multipart body over HTTPS - so the encoder and the SSL context
live here instead of being duplicated per backend.
"""

import json
import mimetypes
import os
import ssl
import urllib.error
import urllib.request
import uuid

# Decky Loader ships its own bundled Python which does not know where
# SteamOS keeps its CA certificates, so default HTTPS verification fails
# with CERTIFICATE_VERIFY_FAILED.  Point the SSL context at the system
# bundle explicitly, falling back to library defaults.
_CA_CANDIDATES = (
    "/etc/ssl/certs/ca-certificates.crt",   # SteamOS / Arch / Debian
    "/etc/pki/tls/certs/ca-bundle.crt",     # Fedora
    "/etc/ssl/cert.pem",                    # others
)


def _make_ssl_context() -> ssl.SSLContext:
    for path in _CA_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:
                pass
    return ssl.create_default_context()


SSL_CTX = _make_ssl_context()


# Discord sits behind Cloudflare, which blocks urllib's default
# "Python-urllib/3.x" agent outright - every webhook call comes back as
# HTTP 403, Cloudflare error 1010.  So identify properly on every
# request; Discord's API docs ask for roughly this shape, and it costs
# nothing anywhere else.
USER_AGENT = ("Deckygram (https://github.com/novasound6945/deckygram, 1.0)")


class Unreachable(Exception):
    """Connection-level failure - no verdict from the server."""


def multipart(fields: dict, files: dict):
    """Encode fields + files. `files` maps a form name to a filesystem path."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, name, value)).encode("utf-8")
    for name, path in files.items():
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                 "Content-Type: %s\r\n\r\n"
                 % (boundary, name, os.path.basename(path), ctype)).encode("utf-8")
        with open(path, "rb") as f:
            body += f.read()
        body += b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    return bytes(body), "multipart/form-data; boundary=%s" % boundary


def request(url: str, fields: dict = None, files: dict = None,
            json_body: dict = None, timeout: int = 600):
    """POST (or GET) and return (status, parsed_json_or_None).

    A response body that is not JSON comes back as None; callers that
    care about the text should not be using this helper.  Raises
    Unreachable when the connection itself failed - that is always worth
    retrying, unlike anything the server actually answered.
    """
    head = {"User-Agent": USER_AGENT}
    if files is not None:
        body, ctype = multipart(fields or {}, files)
        head["Content-Type"] = ctype
        req = urllib.request.Request(url, data=body, headers=head)
    elif json_body is not None or fields:
        head["Content-Type"] = "application/json"
        payload = json_body if json_body is not None else fields
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=head)
    else:
        req = urllib.request.Request(url, headers=head)

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            status = resp.getcode()
            try:
                return status, json.load(resp)
            except Exception:
                return status, None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, None
    except Exception as e:
        raise Unreachable(str(e))
