"""Exact public supplier downloaders for progressive 360 sources."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

from diamond360.d360_source import PACK_COUNTS

from .errors import InvalidPayloadError, MissingEvidenceError
from .models import ROTATION, EvidenceReference, RawEvidence, SourceResponse
from .motion import decode_vision360_scramble
from .protocols import HttpClient


_ITEM_ID = re.compile(r"^(?!.*\.\.)(?=.*[A-Za-z0-9])[A-Za-z0-9_.-]+$")


def _response_json(http: HttpClient, url: str, *, timeout: float, source: str):
    response = http.get(url, timeout=timeout)
    if response.status_code == 404:
        raise MissingEvidenceError(f"{source} resource returned HTTP 404: {url}")
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"{source} resource returned HTTP {response.status_code}: {url}")
    try:
        data = json.loads(response.content)
    except Exception as exc:
        raise InvalidPayloadError(f"{source} resource is not valid JSON: {url}") from exc
    retained = SourceResponse(
        source=source,
        body=response.content,
        locator=response.url,
        media_type=response.headers.get("Content-Type"),
        sanitized=True,
    )
    return data, retained


def _bootstrap_contract(bootstrap, *, source: str):
    if not isinstance(bootstrap, dict):
        raise InvalidPayloadError(f"{source} 0.json must be an object")
    try:
        width = int(bootstrap["width"])
        height = int(bootstrap["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidPayloadError(f"{source} 0.json is missing valid dimensions") from exc
    if width <= 0 or height <= 0:
        raise InvalidPayloadError(f"{source} 0.json dimensions must be positive")
    encrypted = bootstrap.get("scramble")
    if not isinstance(encrypted, str):
        raise InvalidPayloadError(f"{source} 0.json is missing encrypted scramble metadata")
    try:
        scramble = decode_vision360_scramble(encrypted)
    except ValueError as exc:
        raise InvalidPayloadError(f"{source} scramble is invalid: {exc}") from exc
    version = bootstrap.get("version")
    if isinstance(version, bool) or not isinstance(version, (int, str)):
        raise InvalidPayloadError(f"{source} 0.json has invalid version")
    version_text = str(version)
    if not version_text or not version_text.isdigit():
        raise InvalidPayloadError(f"{source} 0.json has invalid version")
    return (width, height), scramble, version_text


class _ProgressiveDownloader:
    source_name: str

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        raise NotImplementedError

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind != ROTATION or not reference.locator:
            return False
        try:
            self._source(reference)
            return True
        except ValueError:
            return False

    def download(self, reference: EvidenceReference) -> RawEvidence:
        viewer, source_root, bootstrap_url = self._source(reference)
        bootstrap, retained = _response_json(
            self.http_client,
            bootstrap_url,
            timeout=self.timeout,
            source=self.source_name,
        )
        dimensions, scramble, version = _bootstrap_contract(
            bootstrap,
            source=self.source_name,
        )
        responses = [retained]
        batches = []
        for batch_number, expected_count in enumerate(PACK_COUNTS, 1):
            url = self._batch_url(source_root, batch_number, version)
            payload, source_response = _response_json(
                self.http_client,
                url,
                timeout=self.timeout,
                source=self.source_name,
            )
            if (
                not isinstance(payload, list)
                or len(payload) != expected_count
                or not all(isinstance(item, str) for item in payload)
            ):
                raise InvalidPayloadError(
                    f"{self.source_name} batch {batch_number} expected "
                    f"{expected_count} base64 JPEG frames"
                )
            responses.append(source_response)
            batches.append(
                {
                    "batch": batch_number,
                    "source_url": url,
                    "frames": payload,
                }
            )

        bundle = {
            "schema_version": "sparkles-progressive-motion/1",
            "source": self.source_name,
            "viewer_url": viewer,
            "dimensions": list(dimensions),
            "scramble": scramble,
            "batches": batches,
        }
        if "front" in bootstrap:
            bundle["face_up_hint"] = bootstrap["front"]
        metadata = dict(reference.metadata)
        metadata.update(
            {
                "supplier": self.source_name,
                "source_root": source_root,
                "source_version": version,
            }
        )
        return RawEvidence(
            reference=reference,
            payload=json.dumps(bundle, separators=(",", ":")).encode(),
            media_type="application/json",
            format="progressive-rotation-json",
            metadata=metadata,
            source_responses=tuple(responses),
        )

    @staticmethod
    def _batch_url(source_root: str, batch_number: int, version: str) -> str:
        return f"{source_root}/{batch_number}.json?version={version}"


class DiajewelRotationDownloader(_ProgressiveDownloader):
    source_name = "diajewel"

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        values = parse_qs(parts.query).get("d", [])
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != "vision.diajewel360.com"
            or parts.path.lower() != "/vision360.html"
            or len(values) != 1
            or not _ITEM_ID.fullmatch(values[0])
        ):
            raise ValueError("not an exact Diajewel Vision360 URL")
        item_id = values[0]
        viewer = f"https://vision.diajewel360.com/Vision360.html?d={item_id}"
        source_root = f"https://vision.diajewel360.com/imaged/{item_id}"
        return viewer, source_root, f"{source_root}/0.json"


class WorkshopRotationDownloader(_ProgressiveDownloader):
    source_name = "workshop"

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        if parts.scheme != "https" or parts.netloc.lower() != "workshop.360view.link":
            raise ValueError("not a Workshop/Core360 URL")

        item_id: str | None = None
        path = parts.path.rstrip("/")
        if path.startswith("/view/"):
            item_id = path.split("/", 2)[2]
        elif path.lower() == "/360viewer/360view.html":
            values = parse_qs(parts.query).get("d", [])
            if len(values) == 1:
                item_id = values[0]
        if not item_id or not _ITEM_ID.fullmatch(item_id):
            raise ValueError("Workshop/Core360 URL is missing a valid exact item ID")

        viewer = f"https://workshop.360view.link/view/{item_id}"
        source_root = f"https://data1.360view.link/data/1/imaged/{item_id}"
        return viewer, source_root, f"{source_root}/0.json?version="
