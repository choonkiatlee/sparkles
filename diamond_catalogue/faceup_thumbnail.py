"""Automatically generate provenance-traced Asscher overview icons from saved frames.

Select the *outer* stone contour using existing geometry, not the bright table.
Use the existing complete-sequence pose/face-lobe policy before claiming a
likely crown-facing view. Images remain colour originals until the final crop.

The output is display-only and makes no assertion of a calibrated face-up angle.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from diamond360 import asscher_pose, asscher_pose_sequence, asscher_outer_octagon
from diamond360 import segmentation
from diamond_retrieval.http import UrllibHttpClient

SCHEMA = "sparkles-faceup-thumbnail-candidate/1"
SIZE = 128
ANALYSIS_SIZE = 320
SAMPLES = 32
MAX_SOURCE_BYTES = 6 * 1024 * 1024
# Face-pose confidence is recorded as metadata, never advertised as verified.


@dataclass(frozen=True)
class SourceFrame:
    position: int
    source_index: int
    stored_position: int | None
    source_sha256: str
    source_url: str


def source_frames(manifest: dict, *, sample_count: int = SAMPLES) -> list[SourceFrame]:
    """Uniformly sample a declared complete ordered cycle, not arbitrary stills."""
    motions = [
        item for item in manifest.get("evidence", [])
        if item.get("kind") == "rotation" and item.get("status") == "success"
        and item.get("metadata", {}).get("sequence_complete") is True
        and len(item.get("frames", [])) >= 16
    ]
    if not motions:
        return []
    frames = motions[0]["frames"]
    size = len(frames)
    if not (16 <= sample_count <= size):
        raise ValueError("Need 16 to N uniformly spaced candidate frames")
    positions = [index * size // sample_count for index in range(sample_count)]
    if len(set(positions)) != sample_count:
        raise ValueError("Sample positions are not distinct")
    result = []
    for position in positions:
        frame = frames[position]
        asset = frame["asset"]
        url = asset.get("storage", {}).get("url")
        digest = asset.get("sha256")
        parsed = urlsplit(url or "")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Saved frame has no trusted public HTTPS URL")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            c not in "0123456789abcdef" for c in digest
        ):
            raise ValueError("Saved frame has invalid SHA-256")
        result.append(SourceFrame(
            position=position, source_index=int(frame["source_index"]),
            stored_position=frame.get("stored_position"),
            source_sha256=digest, source_url=url,
        ))
    return result


def verified_image(payload: bytes, source: SourceFrame) -> Image.Image:
    if not payload or len(payload) > MAX_SOURCE_BYTES:
        raise ValueError("Source frame bytes missing or over safe bound")
    if sha256(payload).hexdigest() != source.source_sha256:
        raise ValueError("Source media SHA-256 mismatch; refusing derivative")
    try:
        with Image.open(BytesIO(payload)) as image:
            if image.width * image.height > 9_000_000:
                raise ValueError("Source image exceeds pixel budget")
            return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Source media could not be decoded as an image") from exc


def assess_image(image: Image.Image, *, position: int) -> dict:
    """Build existing silhouette and pose diagnostics from a reduced RGB copy."""
    reduced = image.copy()
    reduced.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.Resampling.LANCZOS)
    rgb = np.asarray(reduced.convert("RGB"))
    seg = segmentation.segment(rgb)
    if seg["status"] == "failed":
        assessment = {
            "status": "failed", "score": 0.0, "outline": None,
            "components": {}, "reasons": seg["reasons"],
        }
    else:
        assessment = asscher_pose.assess_frame(seg["mask"])
        if assessment["status"] != "failed":
            brightness = (
                rgb.astype(float) / 255.0
                @ np.array([0.2126, 0.7152, 0.0722], dtype=float)
            )
            assessment["face_orientation_cues"] = asscher_pose.face_orientation_cues(
                brightness, seg["mask"], assessment["outline"],
            )
    # Public method consumes existing result schemas, no thumbnail-specific model.
    record = {"position": position, "assessment": assessment,
              "face_role": "unresolved"}
    outer = asscher_outer_octagon.assess_record(record)
    return {"record": record, "outer": outer, "segmentation_status": seg["status"],
            "segmentation_reasons": list(seg.get("reasons", [])),
            "analysis_dimensions": [reduced.width, reduced.height]}


def choose_frame(assessments: list[dict], *, sequence_complete: bool) -> dict:
    """Prefer an outer-supported crown lobe, otherwise a usable display-only view."""
    records = [a["record"] for a in assessments]
    if len(records) < 16 or [r["position"] for r in records] != list(range(len(records))):
        return {"status": "unavailable", "reason": "incomplete_sample_set"}
    face = asscher_pose_sequence.resolve_face_lobes(
        records, sequence_complete=sequence_complete,
    )
    size = len(records)
    crown = face.get("likely_crown_peak_position")
    radius = face.get("lobe_radius_frames", 0)
    crown_candidates = []
    robust_candidates = []
    review_candidates = []
    for i, detail in enumerate(assessments):
        assessment = records[i]["assessment"]
        outer = detail["outer"]
        if assessment.get("outline") is None or detail["segmentation_status"] == "failed":
            continue
        review_candidates.append(i)
        if assessment["status"] in {"ok", "review"} and outer["hard_usable"]:
            robust_candidates.append(i)
            if face.get("status") == "resolved":
                dist = min(abs(i - crown), size - abs(i - crown))
                if dist <= radius:
                    crown_candidates.append(i)
    if crown_candidates:
        candidates = crown_candidates
        method = "outer_verified_crown_lobe"
    elif robust_candidates:
        candidates = robust_candidates
        method = "outer_usable_face_unresolved"
    elif review_candidates:
        # Preserve a useful small preview even if no trustworthy crown lobe exists.
        candidates = review_candidates
        method = "rejected_outer_geometry_review_only"
    else:
        return {"status": "unavailable", "reason": "no_segmented_outer_contour",
                "face_selection": face}
    selected = min(candidates, key=lambda i: (
        assessments[i]["outer"].get("face_on_error", float("inf")),
        -records[i]["assessment"]["score"], i,
    ))
    is_crown = method == "outer_verified_crown_lobe"
    return {
        "status": "likely_crown_candidate" if is_crown else "unverified_pose_candidate",
        "reason": face.get("reason", "crown_orientation_not_resolved"),
        "selection_method": method,
        "sample_index": selected,
        "face_selection": face,
        "outer_quality": assessments[selected]["outer"]["quality"],
        "face_on_error": assessments[selected]["outer"].get("face_on_error"),
        "pose_status": records[selected]["assessment"]["status"],
    }


def crop_color_original(image: Image.Image, *, padding: float = 0.12) -> tuple[Image.Image, list[int]]:
    """Re-fit original outer silhouette for crop bounds, preserving colour pixels."""
    assessment = assess_image(image, position=0)
    outline = assessment["record"]["assessment"]["outline"]
    # When the octagon fit rejects, crop to the observed foreground envelope.
    # Never choose the bright interior table as the diamond boundary.
    reduced = image.copy()
    reduced.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.Resampling.LANCZOS)
    segmented = segmentation.segment(np.asarray(reduced.convert("RGB")))
    if outline and assessment["outer"]["hard_usable"]:
        bounds = np.asarray(outline["vertices_xy"], float)
    elif segmented["status"] != "failed" and int(segmented["mask"].sum()) > 100:
        ys,xs=np.nonzero(segmented["mask"])
        bounds = np.asarray([[xs.min(),ys.min()],[xs.max(),ys.max()]],float)
    else:
        raise ValueError("No reliable contour even for an unverified preview")
    src_w, src_h = image.size
    w, h = assessment["analysis_dimensions"]
    corners = bounds.copy()
    corners[:, 0] *= src_w / w
    corners[:, 1] *= src_h / h
    left, top = corners.min(axis=0)
    right, bottom = corners.max(axis=0)
    cx, cy = (left + right) / 2, (top + bottom) / 2
    side = max(right - left, bottom - top) * (1 + 2 * padding)
    x0 = max(0, int(np.floor(cx - side / 2)))
    y0 = max(0, int(np.floor(cy - side / 2)))
    x1 = min(src_w, int(np.ceil(cx + side / 2)))
    y1 = min(src_h, int(np.ceil(cy + side / 2)))
    if min(x1 - x0, y1 - y0) < 32 or min(x0, y0, src_w - x1, src_h - y1) < 0:
        raise ValueError("Invalid cropped silhouette bounding box")
    # Square output canvas, rather than stretching a nonsquare source region.
    # The full diamond is retained, including any real geometric asymmetry.
    region = image.crop((x0, y0, x1, y1))
    canvas = Image.new("RGB", (max(region.size),) * 2, (242, 243, 239))
    canvas.paste(region, ((canvas.width - region.width)//2,
                          (canvas.height - region.height)//2))
    return canvas, [x0, y0, x1, y1]


def encode_icon(image: Image.Image, size: int = SIZE) -> bytes:
    if not 64 <= size <= 256:
        raise ValueError("Thumbnail size must be within 64–256 pixels")
    icon = image.resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    icon.save(output, format="WEBP", quality=88, method=6)
    return output.getvalue()


def _still_fallback(manifest: dict, fetch_bytes):
    """Try a source-verified still when complete rotation evidence is unavailable."""
    for still in manifest.get("evidence", []):
        if still.get("kind") != "still" or still.get("status") != "success":
            continue
        asset = still.get("payload_asset") or {}
        url=(asset.get("storage") or {}).get("url")
        digest=asset.get("sha256")
        if not url or not digest:
            continue
        source=SourceFrame(-1,-1,None,digest,url)
        image=verified_image(fetch_bytes(url),source)
        try:
            crop,bbox=crop_color_original(image)
        except ValueError:
            continue
        payload=encode_icon(crop)
        return ({
            "schema":SCHEMA,"diamond_id":manifest["id"],
            "status":"unverified_still_crop","pose_verification":"not_calibrated",
            "algorithm":{"silhouette":"diamond360.geometry.fit_asscher_outline",
                         "segmentation":"diamond360.segmentation.segment",
                         "sampling":"single_still"},
            "source":{"evidence_kind":"still","sha256":digest},
            "derivative":{"media_type":"image/webp","sha256":sha256(payload).hexdigest(),
                "byte_count":len(payload),"size_px":SIZE,
                "crop_source_bbox_xyxy":bbox,"padding_fraction":0.12,
                "colour_source":"original_source_RGB",
                "physical_angle_calibrated":False},
        },payload,crop)
    return ({"schema":SCHEMA,"diamond_id":manifest["id"],
             "status":"unavailable","reason":"no_suitable_original_media"},None,None)


def generate_candidate(manifest: dict, *, fetch_bytes, sample_count: int = SAMPLES) -> tuple[dict, bytes | None, Image.Image | None]:
    """Compute a deterministic thumbnail; caller decides whether to publish."""
    sources = source_frames(manifest, sample_count=sample_count)
    if not sources:
        return _still_fallback(manifest, fetch_bytes)
    analyses = []
    cache = {}
    for i, frame in enumerate(sources):
        payload = fetch_bytes(frame.source_url)
        image = verified_image(payload, frame)
        cache[i] = image
        detail = assess_image(image, position=i)
        analyses.append(detail)
    selection = choose_frame(analyses, sequence_complete=True)
    summary = {
        "schema": SCHEMA,
        "diamond_id": manifest["id"],
        "status": selection["status"],
        "pose_verification": "not_calibrated",
        "algorithm": {
            "segmentation": "diamond360.segmentation.segment",
            "silhouette": "diamond360.geometry.fit_asscher_outline",
            "pose": asscher_pose.SCHEMA,
            "face_lobes": asscher_pose_sequence.SEQUENCE_SCHEMA,
            "outer": asscher_outer_octagon.SCHEMA,
            "sampling": "uniform_cyclic_stratified",
            "sample_count": len(sources),
            "original_frame_count": len(next(e for e in manifest["evidence"] if
                e["kind"] == "rotation" and e["status"] == "success"
                and e.get("metadata", {}).get("sequence_complete") is True)["frames"]),
        },
        "selection": {k:v for k,v in selection.items() if k not in {"face_selection"}},
        "face_selection": selection.get("face_selection"),
        "candidate_summaries": [
            {"position": source.position, "source_index": source.source_index,
             "assessment": detail["record"]["assessment"]["status"],
             "pose_score": round(float(detail["record"]["assessment"]["score"]), 4),
             "outer_status": detail["outer"]["status"],
             "outer_face_on_error": round(float(detail["outer"].get("face_on_error", 999)), 4)}
            for source,detail in zip(sources,analyses)
        ],
    }
    if selection["status"] == "unavailable":
        return _still_fallback(manifest, fetch_bytes)
    picked = sources[selection["sample_index"]]
    cropped, bbox = crop_color_original(cache[selection["sample_index"]])
    payload = encode_icon(cropped)
    summary["source"] = {
        "evidence_kind": "rotation",
        "frame_position": picked.position, "source_index": picked.source_index,
        "stored_position": picked.stored_position,
        "sha256": picked.source_sha256,
    }
    summary["derivative"] = {
        "media_type": "image/webp", "sha256": sha256(payload).hexdigest(),
        "byte_count": len(payload), "size_px": SIZE,
        "crop_source_bbox_xyxy": bbox,
        "padding_fraction": 0.12,
        "colour_source": "original_source_RGB",
        "physical_angle_calibrated": False,
    }
    return summary, payload, cropped


def retrieve_frame_bytes(url: str) -> bytes:
    response = UrllibHttpClient(max_bytes=MAX_SOURCE_BYTES).get(url, timeout=30.0)
    if response.status_code != 200:
        raise ValueError(f"Original published media request returned HTTP {response.status_code}")
    return response.content


def preview_manifest(manifest: dict, directory: Path, *, fetch_bytes=retrieve_frame_bytes) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    record, thumbnail, large = generate_candidate(manifest, fetch_bytes=fetch_bytes)
    stem = manifest["id"]
    if thumbnail:
        (directory / f"{stem}.webp").write_bytes(thumbnail)
        large.thumbnail((500,500),Image.Resampling.LANCZOS)
        large.save(directory / f"{stem}-crop.jpg", quality=92)
        # Explicitly show the opposite end of the archived full rotation:
        # face-on silhouettes can appear on both crown AND pavilion sides.
        source = record.get("source") or {}
        if source.get("evidence_kind") == "rotation":
            complete = next((
                e for e in manifest.get("evidence",[])
                if e.get("kind") == "rotation" and e.get("status") == "success"
                and e.get("metadata",{}).get("sequence_complete") is True
            ), None)
            frames = (complete or {}).get("frames",[])
            if len(frames) >= 16:
                alternate_position = (int(source["frame_position"]) + len(frames)//2) % len(frames)
                alternate = frames[alternate_position]
                ref = alternate["asset"]
                alt_source = SourceFrame(
                    position=alternate_position,
                    source_index=int(alternate["source_index"]),
                    stored_position=alternate.get("stored_position"),
                    source_sha256=ref["sha256"],
                    source_url=ref["storage"]["url"],
                )
                try:
                    original = verified_image(fetch_bytes(alt_source.source_url), alt_source)
                    opposite_crop, opposite_bbox = crop_color_original(original)
                    opposite_crop.thumbnail((500,500), Image.Resampling.LANCZOS)
                    opposite_crop.save(directory / f"{stem}-opposite-crop.jpg",quality=92)
                    record["opposite_review_view"] = {
                        "source_index":alt_source.source_index,
                        "frame_position":alternate_position,
                        "source_sha256":alt_source.source_sha256,
                        "crop_source_bbox_xyxy":opposite_bbox,
                        "note":"Comparator only; do not infer crown/pavilion from half-cycle position alone",
                    }
                except (OSError, ValueError):
                    record["opposite_review_view"] = {
                        "status":"unavailable",
                        "note":"Opposite original-frame crop failed QC; do not infer the face",
                    }
    (directory / f"{stem}.json").write_text(
        json.dumps(record,sort_keys=True,indent=2)+"\n",encoding="utf-8",
    )
    return record
