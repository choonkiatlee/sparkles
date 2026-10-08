"""Exact public supplier downloaders for progressive 360 sources."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

from diamond360.d360_source import PACK_COUNTS

from .errors import InvalidPayloadError, MissingEvidenceError
from .models import ROTATION, EvidenceReference, RawEvidence, SourceResponse
from .motion import decode_vision360_scramble, validate_jpeg_bytes
from .protocols import HttpClient


_ITEM_ID = re.compile(r"^(?!.*\.\.)(?=.*[A-Za-z0-9])[A-Za-z0-9_.-]+$")


def _response_bytes(http: HttpClient, url: str, *, timeout: float, source: str):
    response = http.get(url, timeout=timeout)
    if response.status_code == 404:
        raise MissingEvidenceError(f"{source} resource returned HTTP 404: {url}")
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"{source} resource returned HTTP {response.status_code}: {url}")
    retained = SourceResponse(
        source=source,
        body=response.content,
        locator=response.url,
        media_type=response.headers.get("Content-Type"),
        sanitized=True,
    )
    return response.content, retained


def _response_json(http: HttpClient, url: str, *, timeout: float, source: str):
    raw, retained = _response_bytes(http, url, timeout=timeout, source=source)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise InvalidPayloadError(f"{source} resource is not valid JSON: {url}") from exc
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


class Core360RotationDownloader(_ProgressiveDownloader):
    """Download the validated v360.in same-origin Vision360 variant."""

    source_name = "core360"
    _HOST = re.compile(r"^v360[0-9]+\.v360\.in$", re.IGNORECASE)

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        values = parse_qs(parts.query).get("d", [])
        host = parts.netloc.lower()
        if (
            parts.scheme != "https"
            or not self._HOST.fullmatch(host)
            or parts.path.rstrip("/").lower() != "/vision360.html"
            or len(values) != 1
            or not _ITEM_ID.fullmatch(values[0])
        ):
            raise ValueError("not an exact Core360 v360.in viewer URL")
        item_id = values[0]
        viewer = f"https://{host}/vision360.html?d={item_id}"
        source_root = f"https://{host}/imaged/{item_id}"
        return viewer, source_root, f"{source_root}/0.json?version="



class RemoteV360RotationDownloader(_ProgressiveDownloader):
    """Download Vision360 4.0 frames from an exact viewer and its supplied media root.

    The documented `surl` parameter points to the *parent* of the item
    directory. Only known V360 public CDN paths are accepted here: never
    turn an untrusted viewer parameter into a general-purpose HTTP fetch.
    """

    source_name = "v360-remote"
    _CDN_HOST = re.compile(r"^s[0-9]+\.v360\.in$", re.IGNORECASE)
    _CDN_PATH = re.compile(r"^/images/company/[0-9]+/$")

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        query = parse_qs(parts.query)
        names = query.get("d", [])
        if (
            parts.scheme != "https"
            or parts.netloc.lower() not in {"v360.in", "www.v360.in"}
            or parts.path.rstrip("/").lower() != "/viewer4.0/vision360.html"
            or parts.fragment
            or len(names) != 1
            or not _ITEM_ID.fullmatch(names[0])
        ):
            raise ValueError("not an exact V360 4.0 viewer URL")

        item_id = names[0]
        media_urls = query.get("surl", [])
        if len(media_urls) > 1:
            raise ValueError("V360 viewer has ambiguous media roots")
        if media_urls:
            media = urlsplit(media_urls[0])
            if (
                media.scheme != "https"
                or not self._CDN_HOST.fullmatch(media.netloc)
                or not self._CDN_PATH.fullmatch(media.path)
                or media.query
                or media.fragment
            ):
                raise ValueError("V360 viewer media root is not an allowed public CDN directory")
            source_root = f"https://{media.netloc}{media.path}{item_id}"
        else:
            # The documented default when no remote `surl` is supplied.
            source_root = f"https://v360.in/viewer4.0/imaged/{item_id}"

        return locator, source_root, f"{source_root}/0.json?version="


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


class D360RotationDownloader:
    """Download any exact d360.tech viewer that satisfies the audited wire contract."""

    source_name = "d360-tech"

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0) -> None:
        self.http_client = http_client
        self.timeout = timeout

    @staticmethod
    def _source(reference: EvidenceReference) -> tuple[str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        values = parse_qs(parts.query).get("d", [])
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != "d360.tech"
            or parts.path.rstrip("/").lower() != "/view.html"
            or len(values) != 1
            or not _ITEM_ID.fullmatch(values[0])
        ):
            raise ValueError("not an exact d360.tech viewer URL")
        item_id = values[0]
        return item_id, f"https://media.d360.us/imaged/{item_id}"

    def supports(self, reference: EvidenceReference) -> bool:
        if reference.kind != ROTATION:
            return False
        try:
            self._source(reference)
            return True
        except ValueError:
            return False

    def download(self, reference: EvidenceReference) -> RawEvidence:
        item_id, root = self._source(reference)
        metadata_url = f"{root}/metadata.json"
        bootstrap_url = f"{root}/0.json"
        still_url = f"{root}/still.jpg"

        metadata_raw, metadata_response = _response_bytes(
            self.http_client, metadata_url, timeout=self.timeout, source=self.source_name
        )
        try:
            json.loads(metadata_raw)
        except Exception as exc:
            raise InvalidPayloadError("d360 metadata.json is not valid JSON") from exc

        bootstrap, bootstrap_response = _response_json(
            self.http_client, bootstrap_url, timeout=self.timeout, source=self.source_name
        )
        if not isinstance(bootstrap, dict):
            raise InvalidPayloadError("d360 0.json must be an object")
        try:
            width = int(bootstrap["width"])
            height = int(bootstrap["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidPayloadError("d360 0.json is missing valid dimensions") from exc
        if width <= 0 or height <= 0:
            raise InvalidPayloadError("d360 dimensions must be positive")
        encrypted = bootstrap.get("scramble")
        preview = bootstrap.get("image")
        if not isinstance(encrypted, str) or not isinstance(preview, str):
            raise InvalidPayloadError("d360 0.json is missing image/scramble strings")
        try:
            scramble = decode_vision360_scramble(encrypted)
            preview_bytes = base64.b64decode("".join(preview.split()), validate=True)
        except ValueError as exc:
            raise InvalidPayloadError(f"d360 scramble is invalid: {exc}") from exc
        except Exception as exc:
            raise InvalidPayloadError("d360 preview is not valid Base64") from exc

        still_bytes, still_response = _response_bytes(
            self.http_client, still_url, timeout=self.timeout, source=self.source_name
        )
        if preview_bytes != still_bytes:
            raise InvalidPayloadError("d360 0.json preview and still.jpg disagree")
        if validate_jpeg_bytes(still_bytes) != (width, height):
            raise InvalidPayloadError("d360 still dimensions disagree with 0.json")

        responses = [metadata_response, bootstrap_response, still_response]
        batches = []
        for batch_number, expected_count in enumerate(PACK_COUNTS, 1):
            url = f"{root}/{batch_number}.json"
            payload, source_response = _response_json(
                self.http_client, url, timeout=self.timeout, source=self.source_name
            )
            if (
                not isinstance(payload, list)
                or len(payload) != expected_count
                or not all(isinstance(item, str) for item in payload)
            ):
                raise InvalidPayloadError(
                    f"d360 batch {batch_number} expected {expected_count} base64 JPEG frames"
                )
            responses.append(source_response)
            batches.append(
                {"batch": batch_number, "source_url": url, "frames": payload}
            )

        bundle = {
            "schema_version": "sparkles-progressive-motion/1",
            "source": self.source_name,
            "viewer_url": f"https://d360.tech/view.html?d={item_id}",
            "dimensions": [width, height],
            "scramble": scramble,
            "batches": batches,
        }
        raw_metadata = dict(reference.metadata)
        raw_metadata.update(
            {
                "supplier": self.source_name,
                "item_id": item_id,
                "source_root": root,
                "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
                "bootstrap_sha256": hashlib.sha256(bootstrap_response.body).hexdigest(),
                "still_sha256": hashlib.sha256(still_bytes).hexdigest(),
            }
        )
        return RawEvidence(
            reference=reference,
            payload=json.dumps(bundle, separators=(",", ":")).encode(),
            media_type="application/json",
            format="progressive-rotation-json",
            metadata=raw_metadata,
            source_responses=tuple(responses),
        )
