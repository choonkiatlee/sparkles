"""Network-free processors for PDFs and still images."""
from __future__ import annotations

import hashlib
import re
from io import BytesIO

from PIL import Image
from pypdf import PdfReader

from .models import (
    CERTIFICATE,
    STILL,
    CertificateEvidence,
    EvidenceStatus,
    IdentityObservation,
    ProvenanceStep,
    RawEvidence,
    StillEvidence,
)


def _observation(
    field: str,
    value,
    provenance: tuple[ProvenanceStep, ...],
) -> IdentityObservation:
    return IdentityObservation(field=field, value=value, provenance=provenance)


def _pdf_fields(text: str) -> dict[str, object]:
    fields: dict[str, object] = {}

    report = re.search(
        r"(?:REPORT\s+(?:NUMBER|NO\.?|#)|REPORT\s*#)\s*:?[ ]*([A-Z]{0,3}\d{6,})",
        text,
        re.I,
    )
    if report:
        fields["report_number"] = report.group(1).upper()

    if re.search(r"INTERNATIONAL\s+GEMOLOGICAL\s+INSTITUTE", text, re.I):
        fields["lab"] = "IGI"

    # IGI reports can label this field "Shape and Cutting Style".
    # Previously "AND CUT" matched the beginning of "CUTTING", wrongly
    # extracting the remaining fragment "ting Style" as a stone shape.
    # Only a complete label and a recognized shape can become an identity
    # observation; uncertainty is missing data, not an invented conflict.
    shape_label = re.search(
        r"(?im)^[ \t]*SHAPE(?:[ \t]+AND[ \t]+(?:CUTTING[ \t]+STYLE|CUT))?"
        r"[ \t]*:?[ \t]*(.*)$",
        text,
    )
    if shape_label:
        value = shape_label.group(1).strip()
        if not value:
            remaining = text[shape_label.end():].splitlines()
            value = next((line.strip() for line in remaining if line.strip()), "")
        value = re.sub(r"\s+", " ", value).upper()
        valid_shapes = {
            "ROUND", "ROUND BRILLIANT", "ROUND BRILLIANT CUT",
            "OVAL", "OVAL BRILLIANT", "OVAL MODIFIED BRILLIANT",
            "ASSCHER", "ASSCHER CUT", "EMERALD", "EMERALD CUT",
            "CUSHION", "CUSHION BRILLIANT", "CUSHION MODIFIED BRILLIANT",
            "PRINCESS", "PRINCESS CUT", "RADIANT", "RADIANT CUT",
            "PEAR", "PEAR BRILLIANT", "MARQUISE", "MARQUISE BRILLIANT",
            "HEART", "HEART BRILLIANT",
        }
        if value in valid_shapes:
            fields["shape"] = value

    measurements = re.search(
        r"MEASUREMENTS\s*:?[ ]*"
        r"([0-9.]+)\s*(?:mm)?\s*[xX×-]\s*"
        r"([0-9.]+)\s*(?:mm)?\s*[xX×-]\s*"
        r"([0-9.]+)",
        text,
        re.I,
    )
    if measurements:
        fields["dimensions"] = tuple(
            float(measurements.group(i)) for i in range(1, 4)
        )

    carat = re.search(r"CARAT\s+WEIGHT\s*:?[ ]*([0-9.]+)", text, re.I)
    if carat:
        fields["carat"] = float(carat.group(1))

    colour = re.search(r"COL(?:O|OU)R\s+GRADE\s*:?[ ]*([A-Z]+)", text, re.I)
    if colour:
        fields["colour"] = colour.group(1).upper()

    clarity = re.search(
        r"CLARITY\s+GRADE\s*:?[ ]*(FL|IF|VVS1|VVS2|VS1|VS2|SI1|SI2|I1|I2|I3)",
        text,
        re.I,
    )
    if clarity:
        fields["clarity"] = clarity.group(1).upper()

    if re.search(r"LABORATORY\s+GROWN|LAB\s+GROWN", text, re.I):
        fields["origin"] = "lab-grown"
    elif re.search(r"NATURAL\s+DIAMOND", text, re.I):
        fields["origin"] = "natural"

    return fields


class PdfCertificateProcessor:
    def supports(self, raw: RawEvidence) -> bool:
        return raw.reference.kind == CERTIFICATE and raw.payload.startswith(b"%PDF-")

    def process(self, raw: RawEvidence) -> tuple[CertificateEvidence, ...]:
        sha256 = hashlib.sha256(raw.payload).hexdigest()
        error: str | None = None
        text = ""
        try:
            reader = PdfReader(BytesIO(raw.payload))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:
            error = str(exc)

        fields = _pdf_fields(text) if text else {}
        if not fields.get("report_number") and error is None:
            error = "report number was not extractable from PDF text"

        status = (
            EvidenceStatus.SUCCESS
            if error is None
            else EvidenceStatus.EXTRACTION_FAILED
        )
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                "certificate_pdf",
                raw.reference.locator,
                {"sha256": sha256},
            ),
        )
        observations = tuple(
            _observation(field, value, provenance)
            for field, value in fields.items()
            if field
            in {
                "report_number",
                "lab",
                "origin",
                "shape",
                "carat",
                "colour",
                "clarity",
                "dimensions",
            }
        )
        metadata = {
            "sha256": sha256,
            "media_type": raw.media_type,
            "extraction_status": "ok" if error is None else "failed",
        }
        if error is not None:
            metadata["extraction_error"] = error

        return (
            CertificateEvidence(
                identifier=raw.reference.identifier,
                kind=CERTIFICATE,
                provenance=provenance,
                payload=raw.payload,
                identity_observations=observations,
                metadata=metadata,
                source_responses=raw.source_responses,
                status=status,
                extracted_fields=fields,
            ),
        )


class StillImageProcessor:
    def supports(self, raw: RawEvidence) -> bool:
        return raw.reference.kind == STILL

    def process(self, raw: RawEvidence) -> tuple[StillEvidence, ...]:
        try:
            with Image.open(BytesIO(raw.payload)) as image:
                dimensions = tuple(image.size)
                image.verify()
        except Exception as exc:
            raise ValueError(f"Invalid still image bytes: {exc}") from exc

        sha256 = hashlib.sha256(raw.payload).hexdigest()
        provenance = raw.reference.provenance + (
            ProvenanceStep(
                "still_image",
                raw.reference.locator,
                {"sha256": sha256, "dimensions": dimensions},
            ),
        )
        return (
            StillEvidence(
                identifier=raw.reference.identifier,
                kind=STILL,
                provenance=provenance,
                payload=raw.payload,
                metadata={"sha256": sha256, "media_type": raw.media_type},
                source_responses=raw.source_responses,
                dimensions=dimensions,
            ),
        )
