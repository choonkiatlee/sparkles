"""Storage-neutral catalogue planning contracts (schema v1)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

SCHEMA = "sparkles-diamond-catalogue/1"
INDEX_SCHEMA = "sparkles-diamond-index/1"


class CatalogueError(ValueError):
    """Unsafe or invalid publication/merge."""


@dataclass(frozen=True)
class PlannedAsset:
    """Original source bytes that must exist before a manifest can be committed."""

    asset_id: str
    diamond_id: str
    desired_name: str
    sha256: str
    byte_count: int
    media_type: str
    payload: bytes


@dataclass(frozen=True)
class PublishedAsset:
    """Backend resolution, deliberately separate from GitHub's asset API."""

    sha256: str
    byte_count: int
    backend: str
    locator: str
    url: str


@dataclass(frozen=True)
class PublicationPlan:
    diamond_id: str
    manifest: dict
    assets: tuple[PlannedAsset, ...]


class AssetStorage(Protocol):
    """Structural backend protocol for #107 implementations."""

    def publish(self, assets: tuple[PlannedAsset, ...]) -> Mapping[str, PublishedAsset]:
        ...
