"""Small injected GitHub REST adapter for release assets and atomic Git commits.

All URLs are pinned to GitHub API/uploads hosts. Token is never embedded in URLs
or included in exceptions. The network adapter is replaceable by fake API tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class GitHubError(RuntimeError):
    def __init__(self, status: int, context: str, message: str = ""):
        self.status = status
        self.context = context
        # Never serialize URLs, response bodies, token, or request payloads.
        super().__init__(f"GitHub {context} failed (HTTP {status})"
                         + (f": {message}" if message else ""))


@dataclass
class GitHubAPI:
    token: str
    repo: str
    timeout: float = 30.0

    def __post_init__(self):
        if len(self.repo.split("/")) != 2 or not all(
            part and part.replace("-", "").replace("_", "").isalnum()
            for part in self.repo.split("/")
        ):
            raise ValueError("Expected GitHub repository owner/name")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")

    @property
    def prefix(self) -> str:
        return f"/repos/{self.repo}"

    def _request(self, method: str, path: str, *, payload: Any = None,
                 binary: bytes | None = None,
                 accept: str = "application/vnd.github+json",
                 content_type: str | None = None) -> tuple[int, bytes]:
        if method not in {"GET", "POST", "PATCH"}:
            raise ValueError("Unsupported GitHub HTTP method")
        if path.startswith("https://"):
            parsed = urlsplit(path)
            if parsed.hostname != "uploads.github.com" or parsed.username or parsed.password:
                raise ValueError("External GitHub upload URL is not allowed")
            url = path
        else:
            if not path.startswith(self.prefix + "/"):
                raise ValueError("GitHub path must belong to configured repository")
            url = "https://api.github.com" + path
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sparkles-diamond-catalogue",
        }
        data = binary
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif binary is not None:
            headers["Content-Type"] = content_type or "application/octet-stream"
        request = Request(url, data=data, method=method, headers=headers)
        context = f"{method} {urlsplit(url).path.split('/')[-1]}"
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except HTTPError as exc:
            # HTTP error bodies could include secrets or user-controlled text.
            raise GitHubError(exc.code, context) from None
        except (URLError, TimeoutError) as exc:
            raise GitHubError(0, context, "transport error") from None

    def get_json(self, path: str) -> dict | list:
        _, body = self._request("GET", path)
        return json.loads(body)

    def post_json(self, path: str, data: dict) -> dict:
        _, body = self._request("POST", path, payload=data)
        return json.loads(body)

    def patch_json(self, path: str, data: dict) -> dict:
        _, body = self._request("PATCH", path, payload=data)
        return json.loads(body)

    def get_bytes(self, path: str) -> bytes:
        _, body = self._request("GET", path, accept="application/octet-stream")
        return body

    def post_bytes(self, url: str, payload: bytes, media_type: str) -> dict:
        _, body = self._request(
            "POST", url, binary=payload, content_type=media_type,
            accept="application/vnd.github+json",
        )
        return json.loads(body)
