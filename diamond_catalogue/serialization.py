"""Explicit compact JSON policy; raw HTTP responses and bytes are excluded."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from .models import CatalogueError


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not (-float("inf") < value < float("inf")):
            raise CatalogueError("Non-finite number is not JSON serializable")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CatalogueError("Retrieved timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(k): json_value(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    raise CatalogueError(f"Unsupported catalogue data type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def json_document(value: Any) -> str:
    return json.dumps(json_value(value), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def provenance_steps(steps) -> list[dict]:
    # Do not blindly copy raw provenance.details (may contain arbitrary API data).
    return [{"source": step.source, "locator": step.locator} for step in steps]
