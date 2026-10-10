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

    def _read_bootstrap(self, bootstrap_url: str):
        return _response_json(
            self.http_client, bootstrap_url,
            timeout=self.timeout, source=self.source_name,
        )

    def download(self, reference: EvidenceReference) -> RawEvidence:
        viewer, source_root, bootstrap_url = self._source(reference)
        bootstrap, retained = self._read_bootstrap(bootstrap_url)
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


class FilesOnSkyRotationDownloader(_ProgressiveDownloader):
    """Original Vision360 frames from an exact HTTPS FilesOnSky viewer.

    R05 / IGI LG644442866 source was independently audited on 2026-10-10:
    /v360/Vision360.HTML?d=659844 bootstraps at
    /v360/imaged/659844/0.json?version= (v1, 758x599).
    No supplier HTML parsing or generalized URL rewriting is performed.
    """

    source_name = "filesonsky"
    _HOST = "www.filesonsky.com"
    _ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,90}$")

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        query = parse_qs(parts.query, keep_blank_values=True)
        items = query.get("d", [])
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != self._HOST
            or parts.path.lower() != "/v360/vision360.html"
            or parts.fragment
            or set(query) != {"d"}
            or len(items) != 1
            or not self._ID.fullmatch(items[0])
        ):
            raise ValueError("not an exact FilesOnSky Vision360 viewer URL")
        item = items[0]
        root = f"https://{self._HOST}/v360/imaged/{item}"
        return (
            f"https://{self._HOST}/v360/Vision360.HTML?d={item}",
            root,
            f"{root}/0.json?version=",
        )


class Labgrowns3RotationDownloader(_ProgressiveDownloader):
    """Original progressive frames from a publicly linked labgrowns3 S3 viewer.

    Audited against actual 2026-10-10 source JSON for the R06/R10 reference
    diamonds (versions 2 and 1 respectively). Uses the same verified
    256-frame progressive decoder as other Vision360 variants, not HTML
    scraping or a separately inferred frame sequence.
    """

    source_name = "labgrowns3"
    _HOST = "labgrowns3.s3.ap-southeast-1.amazonaws.com"
    _ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,90}$")

    def _source(self, reference: EvidenceReference) -> tuple[str, str, str]:
        locator = reference.locator or ""
        parts = urlsplit(locator)
        query = parse_qs(parts.query, keep_blank_values=True)
        items = query.get("d", [])
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != self._HOST
            or parts.path.lower() != "/stoneimages360.html"
            or parts.fragment
            or set(query) != {"d"}
            or len(items) != 1
            or not self._ID.fullmatch(items[0])
        ):
            raise ValueError("not an exact public labgrowns3 viewer URL")
        item = items[0]
        root = f"https://{self._HOST}/imaged/{item}"
        return (
            f"https://{self._HOST}/stoneimages360.html?d={item}",
            root,
            f"{root}/0.json?version=",
        )


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
            source_root = f"https://{media.netloc}{media.path}imaged/{item_id}"
        else:
            # The documented default when no remote `surl` is supplied.
            source_root = f"https://v360.in/viewer4.0/imaged/{item_id}"

        return locator, source_root, f"{source_root}/0.json?version="


class WorkshopRotationDownloader(_ProgressiveDownloader):
    source_name = "workshop"

    def _read_bootstrap(self, bootstrap_url: str):
        """A narrow compatibility fallback for the known Core360 0.json path.

        Different supported Vision360 variants use either a trailing empty
        version query or the bare 0.json. Only an actual 404 triggers this
        same-item, same-host fallback. Never retry on 403, malformed JSON,
        missing later batches, or a transport error.
        """
        try:
            return super()._read_bootstrap(bootstrap_url)
        except MissingEvidenceError:
            if not bootstrap_url.endswith("/0.json?version="):
                raise
            return super()._read_bootstrap(bootstrap_url[:-len("?version=")])

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


class D360LegacyCanonicalRotationDownloader:
    """R23's audited no-scramble D360 transport (not a general fallback).

    The exact public vendor player HTML audited in #252 constructs canonical
    progressive positions when bootstrap.scramble is absent, and inserts
    pack-frame serial s at canonical[s]-1. This *only* applies to the pinned
    R23 source below; other D360 viewers keep their original strict contract.

    The vendor's 0.json preview is source frame 0 (600x600), distinct from
    its higher-resolution still.jpg (778x778). Both are separately verified.
    """

    source_name = "d360-legacy-canonical"
    VIEWER = "https://d360.tech/view.html?d=89-AY-8102"
    ROOT = "https://media.d360.us/imaged/89-AY-8102"
    BOOTSTRAP_SHA256 = "c2a1eda06f5250c2e7ec4f698e45e2d041739aff9df881f0abb0c2ff8f34fd34"
    METADATA_SHA256 = "5043aa1508fa5b3e9c8420d63f7bc244bf07a55fadf5a8e58ab3e694b86d68a5"
    PREVIEW_SHA256 = "39cd59e0a7d85450be189a233149871245f01d54af034a8cef0f3298dd417191"
    STILL_SHA256 = "ffe7dfcdc03d703a0dbbdfe34cffabe06fe44551c3e4c089afbfdf95b891264b"

    def __init__(self, http_client: HttpClient, *, timeout: float = 20.0):
        self.http_client = http_client
        self.timeout = timeout

    def supports(self, reference: EvidenceReference) -> bool:
        return (
            reference.kind == ROTATION
            and reference.locator == self.VIEWER
        )

    def download(self, reference: EvidenceReference) -> RawEvidence:
        if not self.supports(reference):
            raise ValueError("not the exact audited R23 legacy D360 viewer")
        # A Loupe/Nivoda report-resolved candidate must retain the same
        # reported identity. Normal reference-publication identity validation
        # remains authoritative; this check is additional fail-closed safety.
        report = reference.metadata.get("report_number")
        lab = reference.metadata.get("lab")
        if report is not None and str(report).upper() != "13534682":
            raise InvalidPayloadError("R23 legacy D360 report anchor mismatch")
        if lab is not None and str(lab).upper() != "GIA":
            raise InvalidPayloadError("R23 legacy D360 lab anchor mismatch")

        responses = []
        metadata_raw, response = _response_bytes(
            self.http_client, self.ROOT + "/metadata.json",
            timeout=self.timeout, source=self.source_name,
        )
        responses.append(response)
        if hashlib.sha256(metadata_raw).hexdigest() != self.METADATA_SHA256:
            raise InvalidPayloadError("R23 D360 source metadata changed since audit")
        try:
            metadata = json.loads(metadata_raw)
        except Exception as exc:
            raise InvalidPayloadError("R23 D360 metadata JSON is invalid") from exc
        if not isinstance(metadata, dict) or not isinstance(metadata.get("PROPERTIES"), dict):
            raise InvalidPayloadError("R23 D360 metadata shape changed")

        raw_boot, response = _response_bytes(
            self.http_client, self.ROOT + "/0.json",
            timeout=self.timeout, source=self.source_name,
        )
        responses.append(response)
        if hashlib.sha256(raw_boot).hexdigest() != self.BOOTSTRAP_SHA256:
            raise InvalidPayloadError("R23 D360 bootstrap changed since ordering audit")
        try:
            bootstrap = json.loads(raw_boot)
        except Exception as exc:
            raise InvalidPayloadError("R23 D360 bootstrap is not JSON") from exc
        if not isinstance(bootstrap, dict) or "scramble" in bootstrap:
            raise InvalidPayloadError("R23 D360 no-scramble source contract changed")
        try:
            dimensions = (int(bootstrap["width"]), int(bootstrap["height"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidPayloadError("R23 D360 bootstrap dimensions missing") from exc
        if dimensions != (600, 600):
            raise InvalidPayloadError("R23 D360 frame dimensions changed")
        try:
            preview = base64.b64decode(
                "".join(bootstrap["image"].split()), validate=True,
            )
        except Exception as exc:
            raise InvalidPayloadError("R23 D360 preview is malformed") from exc
        if (hashlib.sha256(preview).hexdigest() != self.PREVIEW_SHA256
                or validate_jpeg_bytes(preview) != dimensions):
            raise InvalidPayloadError("R23 D360 source preview changed")

        still_bytes, response = _response_bytes(
            self.http_client, self.ROOT + "/still.jpg",
            timeout=self.timeout, source=self.source_name,
        )
        responses.append(response)
        if (hashlib.sha256(still_bytes).hexdigest() != self.STILL_SHA256
                or validate_jpeg_bytes(still_bytes) != (778, 778)):
            raise InvalidPayloadError("R23 D360 separate vendor still changed")
        # Do not assume still.jpg matches the embedded 600x600 preview:
        # this audited vendor variant deliberately supplies different originals.

        bundles = []
        original_hashes = set()
        for number, count in enumerate(PACK_COUNTS, 1):
            url = self.ROOT + f"/{number}.json"
            batch, source_response = _response_json(
                self.http_client, url, timeout=self.timeout,
                source=self.source_name,
            )
            if (not isinstance(batch, list) or len(batch) != count
                    or not all(isinstance(frame, str) for frame in batch)):
                raise InvalidPayloadError(
                    f"R23 D360 original pack {number} is incomplete"
                )
            for position, frame in enumerate(batch):
                try:
                    jpeg = base64.b64decode("".join(frame.split()), validate=True)
                except Exception as exc:
                    raise InvalidPayloadError(
                        "R23 D360 original pack contains invalid JPEG Base64"
                    ) from exc
                if validate_jpeg_bytes(jpeg) != dimensions:
                    raise InvalidPayloadError(
                        "R23 D360 original frame dimensions disagree with source"
                    )
                if number == 1 and position == 0 and jpeg != preview:
                    raise InvalidPayloadError(
                        "R23 D360 first original frame differs from vendor preview"
                    )
                digest = hashlib.sha256(jpeg).hexdigest()
                if digest in original_hashes:
                    raise InvalidPayloadError("R23 D360 duplicate original frame bytes")
                original_hashes.add(digest)
            bundles.append({"batch": number, "source_url": url, "frames": batch})
            responses.append(source_response)
        if len(original_hashes) != 256:
            raise InvalidPayloadError("R23 D360 original 256-frame set incomplete")

        # An identity-level permutation is the mathematical representation of
        # the *vendor default, unscrambled canonical progression*. This is not
        # asserted to be a scramble field obtained from 0.json.
        identity_levels = [list(range(n)) for n in PACK_COUNTS]
        bundle = {
            "schema_version": "sparkles-progressive-motion/1",
            "source": self.source_name,
            "viewer_url": self.VIEWER,
            "dimensions": [600, 600],
            "ordering_mode": "vendor_canonical_no_scramble",
            "scramble": identity_levels,
            "batches": bundles,
        }
        meta = dict(reference.metadata)
        meta.update({
            "supplier": self.source_name,
            "item_id": "89-AY-8102",
            "source_root": self.ROOT,
            "metadata_sha256": self.METADATA_SHA256,
            "bootstrap_sha256": self.BOOTSTRAP_SHA256,
            "preview_sha256": self.PREVIEW_SHA256,
            "still_sha256": self.STILL_SHA256,
            "vendor_scramble_present": False,
            "ordering_provenance": "exact D360 vendor player code audit, #252",
        })
        return RawEvidence(
            reference=reference,
            payload=json.dumps(bundle, separators=(",", ":")).encode(),
            media_type="application/json",
            format="progressive-rotation-json",
            metadata=meta,
            source_responses=tuple(responses),
        )


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
        # Exact R23 source uses audited vendor-default canonical order, not
        # this downloader's strict encrypted-scramble contract. Keep retriever
        # select_unique deterministic: only one downloader claims that item.
        if reference.locator == D360LegacyCanonicalRotationDownloader.VIEWER:
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
