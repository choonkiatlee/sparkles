import os
import tempfile
import unittest

from diamond_retrieval import (
    CERTIFICATE,
    ROTATION,
    AmbiguousRegistrationError,
    CompletionAssessment,
    DiamondMetadata,
    Evidence,
    EvidenceKind,
    EvidenceReference,
    EvidenceStatus,
    IdentityComparison,
    IdentityConflictError,
    IdentityObservation,
    IdentityOutcome,
    ListingRecord,
    ProvenanceStep,
    RawEvidence,
    ResultStatus,
    RetrievalConfig,
    SourceResponse,
    StandardResultAssembler,
    StandardRetrievalPolicy,
    StrictIdentityValidator,
    UnsupportedInputError,
    retrieve_diamond,
)

URL = "https://example.test/diamond/123"
REPORT = "IGI123456"


def reference(identifier, kind, key=None, locator=None):
    return EvidenceReference(
        identifier=identifier,
        kind=kind,
        retrieval_key=key or identifier,
        locator=locator,
        provenance=(ProvenanceStep("fixture", identifier),),
    )


class FakeProvider:
    def __init__(self, references):
        self.references = tuple(references)

    def supports(self, url):
        return url == URL

    def fetch(self, url):
        return ListingRecord(
            url=url,
            metadata=DiamondMetadata(report_number=REPORT, lab="IGI"),
            references=self.references,
            provenance=(ProvenanceStep("fake-retailer", url),),
        )


class FakeDownloader:
    def __init__(self, supported_kinds=None, fail_keys=()):
        self.supported_kinds = supported_kinds
        self.fail_keys = set(fail_keys)
        self.calls = []

    def supports(self, ref):
        return self.supported_kinds is None or ref.kind in self.supported_kinds

    def download(self, ref):
        self.calls.append(ref.retrieval_key)
        if ref.retrieval_key in self.fail_keys:
            raise RuntimeError("fixture download failure")
        return RawEvidence(ref, ("bytes:" + ref.retrieval_key).encode(), format="fixture")


class FakeProcessor:
    def __init__(self, supported_kinds=None):
        self.supported_kinds = supported_kinds

    def supports(self, raw):
        return self.supported_kinds is None or raw.reference.kind in self.supported_kinds

    def process(self, raw):
        observations = (
            IdentityObservation("report_number", REPORT, provenance=raw.reference.provenance),
            IdentityObservation("lab", "IGI", provenance=raw.reference.provenance),
        )
        return (
            Evidence(
                identifier=raw.reference.identifier,
                kind=raw.reference.kind,
                provenance=raw.reference.provenance,
                payload=raw.payload,
                identity_observations=observations,
                source_responses=raw.source_responses,
            ),
        )


class CertificateOnlyPolicy:
    def select(self, listing, ref):
        return ref.kind == CERTIFICATE

    def assess_completion(self, listing, evidence, attempts, comparisons):
        ok = any(item.kind == CERTIFICATE for item in evidence)
        return CompletionAssessment(ok, () if ok else ("missing certificate",))


class RequireKindPolicy:
    def __init__(self, kind):
        self.kind = kind

    def select(self, listing, ref):
        return ref.kind == self.kind

    def assess_completion(self, listing, evidence, attempts, comparisons):
        ok = any(item.kind == self.kind for item in evidence)
        return CompletionAssessment(ok, () if ok else ("missing requested kind",))


class NoConflictValidator:
    def validate(self, listing, evidence):
        return ()


class ConflictValidator:
    def validate(self, listing, evidence):
        return (
            IdentityComparison(
                "report_number", IdentityOutcome.CONFLICT, (REPORT, "OTHER")
            ),
        )


class SpyAssembler(StandardResultAssembler):
    def __init__(self):
        self.called = False

    def assemble(self, *args, **kwargs):
        self.called = True
        return super().assemble(*args, **kwargs)


class DiamondRetrievalTests(unittest.TestCase):
    def config(
        self,
        refs,
        *,
        policy=None,
        downloaders=None,
        processors=None,
        resolvers=(),
        validator=None,
        assembler=None,
        depth=8,
    ):
        return RetrievalConfig(
            providers=(FakeProvider(refs),),
            resolvers=tuple(resolvers),
            policy=policy or RequireKindPolicy(CERTIFICATE),
            downloaders=tuple(downloaders or (FakeDownloader(),)),
            processors=tuple(processors or (FakeProcessor(),)),
            identity_validator=validator or NoConflictValidator(),
            assembler=assembler or StandardResultAssembler(),
            max_resolution_depth=depth,
        )

    def test_public_api_end_to_end_with_certificate_and_rotation(self):
        refs = [reference("cert", CERTIFICATE), reference("spin", ROTATION)]
        downloader = FakeDownloader()
        config = RetrievalConfig(
            providers=(FakeProvider(refs),),
            policy=StandardRetrievalPolicy(),
            downloaders=(downloader,),
            processors=(FakeProcessor(),),
            identity_validator=StrictIdentityValidator(),
        )
        result = retrieve_diamond(URL, config)
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual([item.kind for item in result.evidence], [CERTIFICATE, ROTATION])
        self.assertEqual(downloader.calls, ["cert", "spin"])
        self.assertTrue(all(item.payload for item in result.evidence))

    def test_certificate_only_policy_never_downloads_motion(self):
        refs = [reference("cert", CERTIFICATE), reference("spin", ROTATION)]
        downloader = FakeDownloader()
        result = retrieve_diamond(
            URL,
            self.config(refs, policy=CertificateOnlyPolicy(), downloaders=(downloader,)),
        )
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(downloader.calls, ["cert"])
        excluded = [x for x in result.attempts if x.reference_identifier == "spin"]
        self.assertEqual(excluded[0].status, EvidenceStatus.NOT_REQUESTED)

    def test_custom_site_downloader_processor_and_evidence_kind_need_no_core_change(self):
        custom = EvidenceKind("spectral-map")
        result = retrieve_diamond(
            URL,
            self.config(
                [reference("custom", custom)],
                policy=RequireKindPolicy(custom),
                downloaders=(FakeDownloader({custom}),),
                processors=(FakeProcessor({custom}),),
            ),
        )
        self.assertEqual(result.status, ResultStatus.COMPLETE)
        self.assertEqual(result.evidence[0].kind, custom)
        self.assertEqual(result.evidence_of_kind(custom), result.evidence)

    def test_ambiguous_registration_fails_explicitly(self):
        config = RetrievalConfig(
            providers=(FakeProvider([]), FakeProvider([])),
            policy=CertificateOnlyPolicy(),
            identity_validator=NoConflictValidator(),
        )
        with self.assertRaises(AmbiguousRegistrationError):
            retrieve_diamond(URL, config)

    def test_unsupported_and_failed_downloads_are_structured(self):
        cert = reference("cert", CERTIFICATE)
        spin = reference("spin", ROTATION)
        downloader = FakeDownloader({CERTIFICATE}, fail_keys={"cert"})
        config = RetrievalConfig(
            providers=(FakeProvider([cert, spin]),),
            policy=StandardRetrievalPolicy(),
            downloaders=(downloader,),
            processors=(FakeProcessor(),),
            identity_validator=NoConflictValidator(),
        )
        result = retrieve_diamond(URL, config)
        statuses = {x.reference_identifier: x.status for x in result.attempts}
        self.assertEqual(statuses["cert"], EvidenceStatus.DOWNLOAD_FAILED)
        self.assertEqual(statuses["spin"], EvidenceStatus.UNSUPPORTED)
        self.assertEqual(result.status, ResultStatus.PARTIAL)

    def test_cycles_and_repeated_references_do_not_duplicate_downloads(self):
        direct = reference("direct", CERTIFICATE, key="asset:cert")
        a = reference("a", CERTIFICATE, key="resolve:a", locator="resolve:a")
        b = reference("b", CERTIFICATE, key="resolve:b", locator="resolve:b")

        class Resolver:
            def supports(self, ref):
                return bool(ref.locator and ref.locator.startswith("resolve:"))

            def resolve(self, listing, ref):
                if ref.locator == "resolve:a":
                    return (b, direct)
                return (a, direct)

        downloader = FakeDownloader()
        result = retrieve_diamond(
            URL,
            self.config(
                [a],
                resolvers=(Resolver(),),
                downloaders=(downloader,),
                depth=5,
            ),
        )
        self.assertEqual(downloader.calls, ["asset:cert"])
        self.assertEqual(len(result.evidence), 1)
        self.assertIn(EvidenceStatus.DUPLICATE, [x.status for x in result.attempts])

    def test_resolution_depth_is_bounded(self):
        start = reference("0", CERTIFICATE, key="resolve:0", locator="0")

        class EndlessResolver:
            def supports(self, ref):
                return True

            def resolve(self, listing, ref):
                n = int(ref.locator) + 1
                return (
                    reference(
                        str(n),
                        CERTIFICATE,
                        key=f"resolve:{n}",
                        locator=str(n),
                    ),
                )

        result = retrieve_diamond(
            URL,
            self.config([start], resolvers=(EndlessResolver(),), depth=2),
        )
        self.assertEqual(result.attempts[-1].status, EvidenceStatus.RESOLUTION_LIMIT)
        self.assertEqual(len(result.attempts), 3)

    def test_policy_is_reapplied_after_resolution(self):
        wrapper = reference(
            "wrapper", CERTIFICATE, key="resolve:wrapper", locator="resolve"
        )
        motion = reference("motion", ROTATION, key="asset:motion")

        class Resolver:
            def supports(self, ref):
                return ref.locator == "resolve"

            def resolve(self, listing, ref):
                return (motion,)

        downloader = FakeDownloader()
        result = retrieve_diamond(
            URL,
            self.config(
                [wrapper],
                policy=CertificateOnlyPolicy(),
                resolvers=(Resolver(),),
                downloaders=(downloader,),
            ),
        )
        self.assertEqual(downloader.calls, [])
        self.assertEqual(result.attempts[-1].status, EvidenceStatus.NOT_REQUESTED)

    def test_supplier_raw_responses_are_retained_in_result(self):
        class ResponseDownloader(FakeDownloader):
            def download(self, ref):
                self.calls.append(ref.retrieval_key)
                return RawEvidence(
                    ref,
                    b"payload",
                    format="fixture",
                    source_responses=(
                        SourceResponse(
                            "supplier",
                            b"sanitized-response",
                            "https://supplier.test/x",
                        ),
                    ),
                )

        result = retrieve_diamond(
            URL,
            self.config(
                [reference("cert", CERTIFICATE)],
                downloaders=(ResponseDownloader(),),
            ),
        )
        self.assertEqual(len(result.raw_responses), 1)
        self.assertEqual(result.raw_responses[0].source, "supplier")
        self.assertEqual(result.raw_responses[0].body, b"sanitized-response")

    def test_identity_conflict_stops_assembly(self):
        assembler = SpyAssembler()
        config = self.config(
            [reference("cert", CERTIFICATE)],
            validator=ConflictValidator(),
            assembler=assembler,
        )
        with self.assertRaises(IdentityConflictError):
            retrieve_diamond(URL, config)
        self.assertFalse(assembler.called)

    def test_framework_creates_no_persistent_files(self):
        with tempfile.TemporaryDirectory() as directory:
            before = set(os.listdir(directory))
            cwd = os.getcwd()
            try:
                os.chdir(directory)
                result = retrieve_diamond(
                    URL, self.config([reference("cert", CERTIFICATE)])
                )
            finally:
                os.chdir(cwd)
            self.assertEqual(result.status, ResultStatus.COMPLETE)
            self.assertEqual(set(os.listdir(directory)), before)

    def test_default_composition_claims_no_production_support_yet(self):
        with self.assertRaises(UnsupportedInputError):
            retrieve_diamond(URL)

    def test_mandatory_generic_byte_validation_cannot_be_disabled_by_policy(self):
        class EmptyDownloader(FakeDownloader):
            def download(self, ref):
                self.calls.append(ref.retrieval_key)
                return RawEvidence(ref, b"", format="fixture")

        result = retrieve_diamond(
            URL,
            self.config(
                [reference("cert", CERTIFICATE)],
                downloaders=(EmptyDownloader(),),
            ),
        )
        self.assertEqual(result.attempts[-1].status, EvidenceStatus.INVALID_PAYLOAD)
        self.assertEqual(result.evidence, ())


if __name__ == "__main__":
    unittest.main()
