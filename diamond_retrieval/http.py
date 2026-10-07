"""Finite public HTTP reads for retrieval adapters."""
from __future__ import annotations

import ipaddress
import socket
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .protocols import HttpResponse


def validate_public_http_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("Only public http(s) URLs are supported")
    if not parts.hostname:
        raise ValueError("URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Credential-bearing URLs are not allowed")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Invalid URL port") from exc

    try:
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve public hostname: {parts.hostname}") from exc
    if not addresses:
        raise ValueError(f"Unable to resolve public hostname: {parts.hostname}")
    for address in addresses:
        raw = address[4][0].split("%", 1)[0]
        ip = ipaddress.ip_address(raw)
        if not ip.is_global:
            raise ValueError(f"Refusing non-public destination: {parts.hostname}")


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_public_http_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


class UrllibHttpClient:
    """Small default HTTP client with public-destination and size checks."""

    def __init__(
        self,
        *,
        user_agent: str = "sparkles-diamond-retrieval/0.1",
        max_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.user_agent = user_agent
        self.max_bytes = max_bytes

    def get(self, url: str, *, timeout: float) -> HttpResponse:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        validate_public_http_url(url)
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "*/*",
            },
            method="GET",
        )
        opener = build_opener(_PublicRedirectHandler())
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            content = exc.read(self.max_bytes + 1)
            if len(content) > self.max_bytes:
                content = content[: self.max_bytes]
            return HttpResponse(
                status_code=exc.code,
                url=exc.geturl(),
                headers=dict(exc.headers.items()),
                content=content,
            )
        with response:
            final_url = response.geturl()
            validate_public_http_url(final_url)
            content = response.read(self.max_bytes + 1)
            if len(content) > self.max_bytes:
                raise ValueError(f"HTTP response exceeds {self.max_bytes} bytes")
            return HttpResponse(
                status_code=response.status,
                url=final_url,
                headers=dict(response.headers.items()),
                content=content,
            )
