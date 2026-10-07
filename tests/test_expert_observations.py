import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "docs/360/external-benchmark/pricescope/expert-observations.json"
SCHEMA_PATH = ROOT / "docs/360/external-benchmark/pricescope/expert-observation.schema.json"
BENCHMARK_PATH = ROOT / "docs/360/external-benchmark/pricescope/benchmark-manifest.json"


def _load(path):
    return json.loads(path.read_text())


def test_expert_observation_corpus_integrity():
    corpus = _load(CORPUS_PATH)
    schema = _load(SCHEMA_PATH)
    benchmark = _load(BENCHMARK_PATH)

    assert corpus["schema_version"] == "sparkles-expert-observations/1"
    assert schema["properties"]["schema_version"]["const"] == corpus["schema_version"]

    observations = corpus["observations"]
    assert len(observations) == 27

    ids = [row["observation_id"] for row in observations]
    assert len(ids) == len(set(ids))

    benchmark_sample_ids = {row["sample_id"] for row in benchmark["samples"]}

    for row in observations:
        assert row["reviewer"]["reviewer_class"] == "expert"
        assert row["source"]["wording_fidelity"] == "catalog_paraphrase"
        assert row["observation"]["explicitness"] == "explicit"

        media = row["source"]["media_linkage"]
        if media is not None:
            assert set(media["benchmark_sample_ids"]) <= benchmark_sample_ids

        mapping = row["machine_mapping"]
        if mapping["status"] == "pending_geometry":
            assert mapping["semantic_entities"] == []
            assert mapping["optical_event_refs"] == []
            assert mapping["mapping_confidence"] is None

        usage = row["validation_usage"]
        if usage["designation"] == "held_out_candidate":
            assert row["sample_id"] in {
                "asscher-eval-glittery",
                "asscher-eval-crispest",
            }
            assert media is not None
            assert media["full_original_verified"] is True
            assert usage["prior_use"] != "none"

        if usage["designation"] == "semantic_principle":
            assert row["sample_id"] is None
            assert row["sample_domain"] == "general_principle"
            assert mapping["status"] == "not_applicable"

    held_out_samples = {
        row["sample_id"]
        for row in observations
        if row["validation_usage"]["designation"] == "held_out_candidate"
    }
    assert held_out_samples == {
        "asscher-eval-glittery",
        "asscher-eval-crispest",
    }

    # Keep all observations on a held-out sample behind the same anti-leakage wall.
    for sample_id in held_out_samples:
        sample_rows = [row for row in observations if row["sample_id"] == sample_id]
        assert sample_rows
        assert all(
            row["validation_usage"]["designation"] == "held_out_candidate"
            for row in sample_rows
        )

    # Explicitly guard the main #82 interpretation boundaries.
    assert not any(row["machine_mapping"]["status"] == "mapped" for row in observations)
    assert not any(row["sample_id"] == "asscher-eval-messy-arrows" for row in observations)
    assert any(row["observation"]["phenomenon"] == "grey_ambiguity" for row in observations)
    assert corpus["coverage"]["held_out_candidate_sample_ids"] == [
        "asscher-eval-glittery",
        "asscher-eval-crispest",
    ]
