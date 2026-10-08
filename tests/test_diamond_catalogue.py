"""Network-free persistence contract tests against #97 dataclass API."""
import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from diamond_catalogue import (
    CatalogueError, InMemoryStorage, build_index, diamond_id, finalize_manifest,
    json_document, merge_manifest, normalize_identity, plan_publication,
)
from diamond_retrieval.models import (
    CERTIFICATE, ROTATION, STILL, VIDEO, CertificateEvidence, DiamondMetadata,
    DiamondResult, EvidenceAttempt, EvidenceStatus, FieldAttribution,
    IdentityComparison, IdentityOutcome, ProvenanceStep, ResultStatus,
    RotationEvidence, RotationFrame, StillEvidence, VideoEvidence,
)


def frame(position, payload=None, source_index=None):
    payload = payload if payload is not None else f"jpeg frame {position}".encode()
    return RotationFrame(
        source_index=position if source_index is None else source_index,
        payload=payload, dimensions=(648, 511), sha256=hashlib.sha256(payload).hexdigest(),
        stored_position=position + 7, source_batch="supplier-batch-a",
    )


def result(url="https://qualitydiamonds.co.uk/listing?d=1", *, report="LG800667394",
           price="3200.50", status=ResultStatus.COMPLETE, evidence=True,
           retrieved_at=None, extra_evidence=()):
    now = retrieved_at or datetime(2026, 10, 8, 7, tzinfo=timezone.utc)
    source = (ProvenanceStep("listing", url, {"client_secret": "do not persist"}),)
    pdf = b"%PDF-1.4\nexample original certificate\n"
    still = b"jpeg actual original still"
    rotation_frames = (frame(5, b"frame-X", source_index=253),
                       frame(6, b"frame-X", source_index=254),
                       frame(7, b"frame-Y", source_index=0))
    ev = (
        CertificateEvidence("cert", CERTIFICATE, source, pdf,
                            metadata={"sha256": hashlib.sha256(pdf).hexdigest(),
                                      "media_type": "application/pdf"},
                            extracted_fields={"report_number": report}),
        StillEvidence("still", STILL, source, still,
                      metadata={"sha256": hashlib.sha256(still).hexdigest(),
                                "media_type": "image/jpeg"}, dimensions=(800, 800)),
        RotationEvidence("spin", ROTATION, source, b"", frames=rotation_frames,
                         face_up_hint={"source_index": 253}),
    ) if evidence else ()
    return DiamondResult(
        listing_url=url,
        metadata=DiamondMetadata(report_number=report, lab="IGI", retailer_sku="retailer123",
                                 origin="lab-grown", shape="Asscher", carat=Decimal("1.21"),
                                 colour="G", clarity="VS1", dimensions=(5.8, 5.8, 3.9),
                                 reported_proportions={"table": "64%"},
                                 price=Decimal(price) if price is not None else None,
                                 currency="GBP", tax_basis="inc-VAT",
                                 attribution={"carat": FieldAttribution("certificate", "https://example.test/cert")}),
        evidence=ev + extra_evidence, provenance=source,
        raw_responses=(b"raw response must never be committed",),
        attempts=(EvidenceAttempt("missing-video", VIDEO, "video-remote", EvidenceStatus.MISSING,
                                  source, "upstream unavailable"),) if status == ResultStatus.PARTIAL else (),
        identity_comparisons=(IdentityComparison("report_number", IdentityOutcome.AGREEMENT,
                                                 (report, report), source),),
        status=status, completion_reasons=("missing video",) if status == ResultStatus.PARTIAL else (),
        retrieved_at=now,
    )


def publish(value, storage=None):
    plan = plan_publication(value)
    backend = storage or InMemoryStorage()
    return plan, finalize_manifest(plan, backend.publish(plan.assets)), backend


class CatalogueTests(unittest.TestCase):
    def test_normalize_identity_conservatively(self):
        self.assertEqual(normalize_identity(" International Gemological Institute ", " lg-800667394 "),
                         ("IGI", "LG800667394"))
        self.assertEqual(diamond_id("igi", "LG800667394"), "igi-lg800667394")
        with self.assertRaises(CatalogueError):
            diamond_id(None, "LG800667394")
        with self.assertRaises(CatalogueError):
            diamond_id("IGI", "LG80/0667394")

    def test_deterministic_network_free_plan_preserves_original_source_hashes(self):
        one = plan_publication(result())
        two = plan_publication(result())
        self.assertEqual(json_document(one.manifest), json_document(two.manifest))
        self.assertEqual(one.assets, two.assets)
        self.assertEqual(one.diamond_id, "igi-lg800667394")
        self.assertEqual(len(one.assets), 4)  # PDF, still, two distinct JPEG frame contents.
        self.assertTrue(all(a.sha256 == hashlib.sha256(a.payload).hexdigest() for a in one.assets))
        self.assertTrue(all(a.desired_name.startswith("asset-") for a in one.assets))
        self.assertTrue(all("/" not in a.desired_name for a in one.assets))
        body = json_document(one.manifest)
        self.assertNotIn("raw response", body)
        self.assertNotIn("client_secret", body)
        self.assertNotIn("frame-X", body)
        self.assertNotIn("asset-", body)  # No backend path speculation in planned manifest.

    def test_rotation_order_source_indices_stored_positions_batches_and_duplicate_bytes(self):
        plan, manifest, backend = publish(result())
        frames = manifest["evidence"][2]["frames"]
        self.assertEqual([f["source_index"] for f in frames], [253, 254, 0])
        self.assertEqual([f["stored_position"] for f in frames], [12, 13, 14])
        self.assertEqual([f["source_batch"] for f in frames], ["supplier-batch-a"] * 3)
        self.assertEqual([f["dimensions"] for f in frames], [[648, 511]] * 3)
        self.assertEqual(frames[0]["asset"], frames[1]["asset"])
        self.assertEqual(frames[0]["asset"]["sha256"], hashlib.sha256(b"frame-X").hexdigest())
        self.assertEqual(backend.upload_count, 4)

    def test_idempotent_republishing_and_merging(self):
        storage = InMemoryStorage()
        plan, published, _ = publish(result(), storage)
        same_plan, same, _ = publish(result(), storage)
        self.assertEqual(storage.upload_count, len(plan.assets))
        self.assertEqual(published, same)
        merged = merge_manifest(published, same)
        self.assertEqual(merged, merge_manifest(None, published))
        self.assertEqual(json_document(merged), json_document(merge_manifest(merged, same)))

    def test_same_certificate_from_another_retailer_preserves_both_listings(self):
        first = publish(result())[1]
        second = publish(result(url="https://diyona.com/pages/diamond-detail?sku=abc", price="3300"))[1]
        merged = merge_manifest(first, second)
        self.assertEqual(merged["id"], first["id"])
        self.assertEqual(len(merged["listings"]), 2)
        self.assertEqual(len(merged["retrievals"]), 2)
        self.assertEqual(len(merged["evidence"]), 6)  # Preserve source provenance, not just source bytes.
        self.assertEqual(len(build_index([merged])["diamonds"]), 1)

    def test_partial_retrieval_cannot_erase_earlier_successful_media(self):
        full = publish(result())[1]
        partial = publish(result(url="https://diyona.com/details?sku=1", status=ResultStatus.PARTIAL,
                                 evidence=False, price=None,
                                 retrieved_at=datetime(2026, 10, 8, 8, tzinfo=timezone.utc)))[1]
        merged = merge_manifest(full, partial)
        self.assertEqual(len(merged["evidence"]), 3)
        self.assertEqual(len(merged["retrievals"]), 2)
        self.assertEqual(build_index([merged])["diamonds"][0]["retrieval_status"], "partial")
        self.assertTrue(build_index([merged])["diamonds"][0]["has_motion"])
        self.assertEqual(merged["retrievals"][-1]["attempts"][0]["message"], "upstream unavailable")

    def test_unresolved_and_conflicting_identity_fails_closed(self):
        with self.assertRaises(CatalogueError):
            plan_publication(replace(result(), metadata=replace(result().metadata, report_number=None)))
        conflicting = replace(result(), identity_comparisons=(
            IdentityComparison("report_number", IdentityOutcome.CONFLICT, ("A", "B")),
        ))
        with self.assertRaises(CatalogueError):
            plan_publication(conflicting)
        old = publish(result())[1]
        changed = publish(result(report="LG800667395"))[1]
        with self.assertRaises(CatalogueError):
            merge_manifest(old, changed)
        changed_metadata = replace(result(), metadata=replace(result().metadata, colour="D"))
        with self.assertRaisesRegex(CatalogueError, "colour"):
            merge_manifest(old, publish(changed_metadata)[1])

    def test_publication_is_commit_last_and_fails_on_missing_or_corrupted_media(self):
        plan = plan_publication(result())
        storage = InMemoryStorage()
        resolved = storage.publish(plan.assets)
        del resolved[plan.assets[0].asset_id]
        with self.assertRaisesRegex(CatalogueError, "not published"):
            finalize_manifest(plan, resolved)
        resolved = storage.publish(plan.assets)
        bad = copy.copy(resolved[plan.assets[0].asset_id])
        resolved[plan.assets[0].asset_id] = replace(bad, sha256="0" * 64)
        with self.assertRaisesRegex(CatalogueError, "does not match"):
            finalize_manifest(plan, resolved)
        fake = copy.deepcopy(plan.manifest)
        with self.assertRaisesRegex(CatalogueError, "Unpublished"):
            merge_manifest(None, fake)

    def test_metadata_and_frame_hash_mismatches_rejected(self):
        original = result()
        broken = replace(original.evidence[2].frames[0], sha256="bad")
        evidence = list(original.evidence)
        evidence[2] = replace(evidence[2], frames=(broken,) + evidence[2].frames[1:])
        with self.assertRaisesRegex(CatalogueError, "SHA-256 mismatch"):
            plan_publication(replace(original, evidence=tuple(evidence)))

    def test_no_bulk_binary_in_catalogue_json(self):
        plan, manifest, storage = publish(result())
        body = json_document(manifest)
        self.assertEqual(json.loads(body), manifest)
        self.assertLess(len(body.encode()), 15000)
        for asset in plan.assets:
            self.assertNotIn(asset.payload.decode(), body)
        self.assertEqual(len(storage.objects), 4)

    def test_storage_backend_neutral_resolved_asset_reference(self):
        a = publish(result(), InMemoryStorage(backend="github_release"))[1]
        b = publish(result(), InMemoryStorage(backend="r2"))[1]
        self.assertEqual(a["schema"], b["schema"])
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(build_index([a])["diamonds"][0]["thumbnail_url"],
                         build_index([b])["diamonds"][0]["thumbnail_url"])
        self.assertEqual(a["evidence"][0]["payload_asset"]["storage"]["backend"], "github_release")
        self.assertEqual(b["evidence"][0]["payload_asset"]["storage"]["backend"], "r2")

    def test_index_is_deterministic_independent_of_manifest_order(self):
        first = publish(result())[1]
        second = publish(result(report="LG800667395"))[1]
        self.assertEqual(build_index([first, second]), build_index([second, first]))
        with self.assertRaisesRegex(CatalogueError, "Multiple manifests"):
            build_index([first, copy.deepcopy(first)])
        self.assertEqual(build_index([first])["diamonds"][0]["report_number"], "LG800667394")

    def test_generic_future_evidence_kind_is_supported(self):
        from diamond_retrieval.models import Evidence, EvidenceKind
        custom = Evidence("aset", EvidenceKind("aset"), (), b"source binary")
        manifest = publish(result(extra_evidence=(custom,)))[1]
        entry = manifest["evidence"][-1]
        self.assertEqual(entry["kind"], "aset")
        self.assertEqual(entry["payload_asset"]["media_type"], "application/octet-stream")


    def test_reviewed_thumbnail_survives_reingestion(self):
        stored = publish(result())[1]
        thumb = {
            "asset":{"sha256":"a"*64,"byte_count":1800,"media_type":"image/webp",
                "storage":{"backend":"r2","locator":"thumb","url":"https://assets.example.test/thumb.webp"}},
            "source":{"sha256":"b"*64,"source_index":0,"frame_position":0},
            "crop_source_bbox_xyxy":[10,10,200,200],
            "generation":{"status":"automatic","algorithm":"v1"},
        }
        stored["derived_media"]={"overview_thumbnail":thumb}
        self.assertEqual(build_index([stored])["diamonds"][0]["overview_thumbnail_url"],
                         "https://assets.example.test/thumb.webp")
        merged = merge_manifest(stored,publish(result(url="https://diyona.com/new?sku=1"))[1])
        self.assertEqual(merged["derived_media"],stored["derived_media"])
        damaged=copy.deepcopy(stored)
        damaged["derived_media"]["overview_thumbnail"]["asset"]["storage"]=None
        with self.assertRaisesRegex(CatalogueError,"Unpublished"):
            build_index([damaged])


if __name__ == "__main__":
    unittest.main()
