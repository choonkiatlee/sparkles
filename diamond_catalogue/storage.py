"""Test-only fake backend. Real GitHub transport belongs in #107."""
from __future__ import annotations

import hashlib
from urllib.parse import quote

from .models import AssetStorage, CatalogueError, PlannedAsset, PublishedAsset


class InMemoryStorage(AssetStorage):
    def __init__(self, backend: str = "github_release", base_url: str = "https://media.example.test"):
        if backend not in {"github_release", "r2"}:
            raise ValueError("Unsupported fake backend")
        self.backend = backend
        self.base_url = base_url.rstrip("/")
        self.objects: dict[str, bytes] = {}
        self.upload_count = 0

    def publish(self, assets: tuple[PlannedAsset, ...]) -> dict[str, PublishedAsset]:
        resolved = {}
        for asset in assets:
            if len(asset.payload) != asset.byte_count or hashlib.sha256(asset.payload).hexdigest() != asset.sha256:
                raise CatalogueError("Original source asset hash/size mismatch")
            key = f"{asset.diamond_id}/{asset.desired_name}"
            if key in self.objects and self.objects[key] != asset.payload:
                raise CatalogueError("Existing storage key has different bytes")
            if key not in self.objects:
                self.objects[key] = asset.payload
                self.upload_count += 1
            resolved[asset.asset_id] = PublishedAsset(
                sha256=asset.sha256, byte_count=asset.byte_count, backend=self.backend,
                locator=key, url=f"{self.base_url}/{quote(key, safe='/')}",
            )
        return resolved
