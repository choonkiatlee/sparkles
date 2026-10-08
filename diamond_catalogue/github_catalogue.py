"""Atomic Git-tree catalogue updates after verified immutable asset uploads."""
from __future__ import annotations
import base64
import hashlib
import json
from dataclasses import dataclass

from .github_api import GitHubError
from .github_release import GitHubReleaseStorage
from .index import build_index
from .merge import merge_manifest
from .models import CatalogueError, PublicationPlan
from .planner import finalize_manifest, plan_publication
from .serialization import json_document

MAX_COMMIT_ATTEMPTS = 3
CATALOGUE_PATH = "data/catalog.json"
MANIFEST_PREFIX = "data/diamonds/"

@dataclass(frozen=True)
class PublishReceipt:
    diamond_id: str
    manifest_path: str
    asset_count: int
    catalogue_count: int
    commit_sha: str | None
    changed: bool
    status: str

class GitHubCatalogue:
    """Commit updated manifest + regenerated index together; retry stale head."""
    def __init__(self, api, branch: str = "master"):
        if branch != "master":
            raise ValueError("v0 catalogue only publishes to master")
        self.api = api
        self.branch = branch

    def _snapshot(self) -> tuple[str, str, dict[str, dict], dict | None]:
        head = self.api.get_json(f"{self.api.prefix}/git/ref/heads/{self.branch}")["object"]["sha"]
        tree_sha = self.api.get_json(f"{self.api.prefix}/git/commits/{head}")["tree"]["sha"]
        tree = self.api.get_json(f"{self.api.prefix}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise CatalogueError("Cannot regenerate index from truncated Git tree")
        manifests = {}
        old_index = None
        for entry in tree["tree"]:
            path = entry["path"]
            if entry["type"] != "blob":
                continue
            if not ((path.startswith(MANIFEST_PREFIX) and path.endswith(".json"))
                    or path == CATALOGUE_PATH):
                continue
            blob = self.api.get_json(f"{self.api.prefix}/git/blobs/{entry['sha']}")
            if blob.get("encoding") != "base64":
                raise CatalogueError("Cannot decode existing Git catalogue JSON")
            try:
                value = json.loads(base64.b64decode(blob["content"], validate=False))
            except (ValueError, UnicodeError) as exc:
                raise CatalogueError("Invalid stored catalogue JSON") from exc
            if path == CATALOGUE_PATH:
                old_index = value
            else:
                manifests[path] = value
        return head, tree_sha, manifests, old_index

    def commit(self, published_manifest: dict, *, asset_count: int) -> PublishReceipt:
        path = MANIFEST_PREFIX + published_manifest["id"] + ".json"
        for attempt in range(MAX_COMMIT_ATTEMPTS):
            head, tree_sha, manifests, old_index = self._snapshot()
            existing = manifests.get(path)
            merged = merge_manifest(existing, published_manifest)
            manifests[path] = merged
            index = build_index(manifests.values())
            if existing == merged and old_index == index:
                return PublishReceipt(
                    published_manifest["id"], path, asset_count, len(manifests),
                    head, False, merged["retrievals"][-1]["status"]
                )
            tree = self.api.post_json(f"{self.api.prefix}/git/trees", {
                "base_tree": tree_sha,
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob",
                     "content": json_document(merged)},
                    {"path": CATALOGUE_PATH, "mode": "100644", "type": "blob",
                     "content": json_document(index)},
                ],
            })
            commit = self.api.post_json(f"{self.api.prefix}/git/commits", {
                "message": f"Catalogue: publish {published_manifest['id']}",
                "tree": tree["sha"], "parents": [head],
            })
            try:
                self.api.patch_json(f"{self.api.prefix}/git/refs/heads/{self.branch}", {
                    "sha": commit["sha"], "force": False,
                })
            except GitHubError as error:
                if error.status not in {409, 422} or attempt + 1 == MAX_COMMIT_ATTEMPTS:
                    raise
                continue
            return PublishReceipt(
                published_manifest["id"], path, asset_count, len(manifests),
                commit["sha"], True, merged["retrievals"][-1]["status"]
            )
        raise CatalogueError("Catalogue commit retries exhausted")

def publish_plan(plan: PublicationPlan, api) -> PublishReceipt:
    for asset in plan.assets:
        if len(asset.payload) != asset.byte_count or hashlib.sha256(asset.payload).hexdigest() != asset.sha256:
            raise CatalogueError("Source asset changed before publication")
    published = GitHubReleaseStorage(api).publish(plan.assets)
    final = finalize_manifest(plan, published)
    return GitHubCatalogue(api).commit(final, asset_count=len(plan.assets))

def publish_result(result, api) -> PublishReceipt:
    return publish_plan(plan_publication(result), api)
