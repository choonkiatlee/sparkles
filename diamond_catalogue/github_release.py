"""Original-byte GitHub Release assets, separate from persisted manifest schema."""
from __future__ import annotations

import hashlib
from urllib.parse import quote, urlsplit

from .github_api import GitHubError
from .models import CatalogueError, PlannedAsset, PublishedAsset

ASSET_LIMIT = 1000
RELEASE_PREFIX = "sparkles-diamond-"


class GitHubReleaseStorage:
    """Idempotent content-hashed assets in one stable release per certified stone.

    The 1,000-asset Release cap is checked before upload. A future sharded
    backend or R2 can implement the same AssetStorage protocol.
    """

    def __init__(self, api):
        self.api = api

    def _tag(self, diamond_id: str) -> str:
        if not diamond_id or not all(c.isalnum() or c == "-" for c in diamond_id):
            raise CatalogueError("Invalid stable diamond ID for release")
        return RELEASE_PREFIX + diamond_id

    def _release(self, tag: str) -> dict:
        path = f"{self.api.prefix}/releases/tags/{quote(tag, safe='')}"
        try:
            return self.api.get_json(path)
        except GitHubError as error:
            if error.status != 404:
                raise
        try:
            return self.api.post_json(f"{self.api.prefix}/releases", {
                "tag_name": tag,
                "target_commitish": "master",
                "name": f"Sparkles original evidence — {tag.removeprefix(RELEASE_PREFIX)}",
                "body": "Immutable original diamond evidence. See the versioned catalogue manifest in Git.",
                "draft": False,
                "prerelease": True,
                "make_latest": "false",
            })
        except GitHubError as error:
            if error.status != 422:
                raise
            # Concurrent Release creation can race; reload the stable tag.
            return self.api.get_json(path)

    def _existing_assets(self, release_id: int) -> dict[str, dict]:
        found = {}
        for page in range(1, 20):
            page_assets = self.api.get_json(
                f"{self.api.prefix}/releases/{release_id}/assets?per_page=100&page={page}"
            )
            if not isinstance(page_assets, list):
                raise CatalogueError("Invalid GitHub Release asset listing")
            for asset in page_assets:
                name = asset["name"]
                if name in found:
                    raise CatalogueError("GitHub Release contains duplicate asset names")
                found[name] = asset
            if len(page_assets) < 100:
                return found
        raise CatalogueError("Release asset enumeration exceeded safe bound")

    def _verify_asset(self, asset: PlannedAsset, published: dict) -> None:
        if published.get("name") != asset.desired_name or published.get("state") != "uploaded":
            raise CatalogueError("GitHub Release asset is not successfully uploaded")
        if published.get("size") != asset.byte_count:
            raise CatalogueError("GitHub Release asset byte count mismatch")
        digest = published.get("digest")
        if digest:
            if digest != "sha256:" + asset.sha256:
                raise CatalogueError("GitHub Release asset digest mismatch")
        else:
            # Older GitHub APIs do not expose digest: verify raw stored bytes.
            raw = self.api.get_bytes(f"{self.api.prefix}/releases/assets/{published['id']}")
            if len(raw) != asset.byte_count or hashlib.sha256(raw).hexdigest() != asset.sha256:
                raise CatalogueError("GitHub Release asset bytes differ from source")

    def publish(self, assets: tuple[PlannedAsset, ...]) -> dict[str, PublishedAsset]:
        if not assets:
            return {}
        ids = {a.diamond_id for a in assets}
        if len(ids) != 1:
            raise CatalogueError("A publication plan must belong to one certified diamond")
        names = {}
        for asset in assets:
            if not asset.payload or asset.byte_count != len(asset.payload):
                raise CatalogueError("Invalid source asset size")
            if hashlib.sha256(asset.payload).hexdigest() != asset.sha256:
                raise CatalogueError("Invalid source asset SHA-256")
            if not asset.desired_name.startswith("asset-" + asset.sha256):
                raise CatalogueError("Asset filename must be content-hashed")
            if "/" in asset.desired_name or "\\" in asset.desired_name:
                raise CatalogueError("Release asset filename must be flat")
            previous = names.setdefault(asset.desired_name, asset.sha256)
            if previous != asset.sha256:
                raise CatalogueError("Conflicting content for one asset filename")

        tag = self._tag(next(iter(ids)))
        release = self._release(tag)
        existing = self._existing_assets(release["id"])
        missing = {a.desired_name for a in assets if a.desired_name not in existing}
        if len(existing) + len(missing) > ASSET_LIMIT:
            raise CatalogueError("GitHub Release would exceed its 1,000-asset limit; use R2 or sharded storage")

        url_template = release.get("upload_url", "")
        upload_url = url_template.split("{", 1)[0]
        parsed = urlsplit(upload_url)
        if parsed.scheme != "https" or parsed.hostname != "uploads.github.com":
            raise CatalogueError("GitHub returned an invalid Release upload URL")

        resolved = {}
        for asset in assets:
            published = existing.get(asset.desired_name)
            if published is None:
                try:
                    published = self.api.post_bytes(
                        upload_url + "?name=" + quote(asset.desired_name, safe=""),
                        asset.payload, asset.media_type,
                    )
                except GitHubError as error:
                    if error.status != 422:
                        raise
                    # Race on existing name: verify rather than overwrite.
                    existing = self._existing_assets(release["id"])
                    published = existing.get(asset.desired_name)
                    if published is None:
                        raise
            self._verify_asset(asset, published)
            url = published.get("browser_download_url", "")
            parsed_url = urlsplit(url)
            if (parsed_url.scheme != "https" or parsed_url.hostname != "github.com"
                    or parsed_url.username or parsed_url.password):
                raise CatalogueError("Invalid public Release asset download URL")
            resolved[asset.asset_id] = PublishedAsset(
                sha256=asset.sha256,
                byte_count=asset.byte_count,
                backend="github_release",
                locator=f"{tag}/{asset.desired_name}",
                url=url,
            )
            existing[asset.desired_name] = published
        return resolved
