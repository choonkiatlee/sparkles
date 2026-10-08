"""Generic constructor-injected retrieval orchestration."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from typing import Sequence

from .errors import (
    IdentityConflictError,
    InvalidPayloadError,
    MissingEvidenceError,
    RetrievalError,
    UnsupportedEvidenceError,
    UnsupportedInputError,
)
from .models import (
    DiamondResult,
    Evidence,
    EvidenceAttempt,
    EvidenceReference,
    EvidenceStatus,
    IdentityOutcome,
    RawEvidence,
)
from .protocols import (
    EvidenceDownloader,
    EvidenceProcessor,
    EvidenceResolver,
    IdentityValidator,
    ListingProvider,
    ResultAssembler,
    RetrievalPolicy,
)
from .registry import select_unique


class DiamondRetriever:
    def __init__(
        self,
        *,
        providers: Sequence[ListingProvider],
        resolvers: Sequence[EvidenceResolver],
        policy: RetrievalPolicy,
        downloaders: Sequence[EvidenceDownloader],
        processors: Sequence[EvidenceProcessor],
        identity_validator: IdentityValidator,
        assembler: ResultAssembler,
        max_resolution_depth: int = 8,
    ) -> None:
        if max_resolution_depth < 0:
            raise ValueError("max_resolution_depth must be non-negative")
        self.providers = tuple(providers)
        self.resolvers = tuple(resolvers)
        self.policy = policy
        self.downloaders = tuple(downloaders)
        self.processors = tuple(processors)
        self.identity_validator = identity_validator
        self.assembler = assembler
        self.max_resolution_depth = max_resolution_depth

    def retrieve(self, url: str) -> DiamondResult:
        provider = select_unique(self.providers, url, role="listing provider")
        if provider is None:
            raise UnsupportedInputError(f"No listing provider supports URL: {url}")
        try:
            listing = provider.fetch(url)
        except UnsupportedInputError:
            raise
        except Exception as exc:
            raise RetrievalError(f"Listing retrieval failed for {url}: {exc}") from exc

        queue: deque[tuple[EvidenceReference, int]] = deque()
        for reference in listing.references:
            queue.append((self._prepend_provenance(reference, listing.provenance), 0))

        attempts: list[EvidenceAttempt] = []
        evidence: list[Evidence] = []
        resolved_keys: set[str] = set()
        downloaded_keys: set[str] = set()

        while queue:
            reference, depth = queue.popleft()
            if not self.policy.select(listing, reference):
                attempts.append(self._attempt(reference, EvidenceStatus.NOT_REQUESTED))
                continue

            resolver = select_unique(self.resolvers, reference, role="evidence resolver")
            if resolver is not None:
                if reference.retrieval_key in resolved_keys:
                    attempts.append(
                        self._attempt(reference, EvidenceStatus.DUPLICATE, "resolution already visited")
                    )
                    continue
                if depth >= self.max_resolution_depth:
                    attempts.append(
                        self._attempt(
                            reference,
                            EvidenceStatus.RESOLUTION_LIMIT,
                            f"maximum resolution depth {self.max_resolution_depth} reached",
                        )
                    )
                    continue
                resolved_keys.add(reference.retrieval_key)
                try:
                    children = tuple(resolver.resolve(listing, reference))
                except Exception as exc:
                    attempts.append(
                        self._attempt(reference, EvidenceStatus.RESOLUTION_FAILED, str(exc))
                    )
                    continue
                if not children:
                    attempts.append(
                        self._attempt(reference, EvidenceStatus.RESOLUTION_FAILED, "resolver returned no references")
                    )
                    continue
                attempts.append(self._attempt(reference, EvidenceStatus.RESOLVED))
                for child in children:
                    queue.append((self._prepend_provenance(child, reference.provenance), depth + 1))
                continue

            if reference.retrieval_key in downloaded_keys:
                attempts.append(
                    self._attempt(reference, EvidenceStatus.DUPLICATE, "asset already downloaded")
                )
                continue

            downloader = select_unique(self.downloaders, reference, role="evidence downloader")
            if downloader is None:
                attempts.append(self._attempt(reference, EvidenceStatus.UNSUPPORTED, "no downloader supports reference"))
                continue
            downloaded_keys.add(reference.retrieval_key)
            try:
                raw = downloader.download(reference)
                self._validate_raw(raw, reference)
            except MissingEvidenceError as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.MISSING, str(exc)))
                continue
            except UnsupportedEvidenceError as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.UNSUPPORTED, str(exc)))
                continue
            except InvalidPayloadError as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.INVALID_PAYLOAD, str(exc)))
                continue
            except Exception as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.DOWNLOAD_FAILED, str(exc)))
                continue

            processor = select_unique(self.processors, raw, role="evidence processor")
            if processor is None:
                attempts.append(self._attempt(reference, EvidenceStatus.UNSUPPORTED, "no processor supports downloaded format"))
                continue
            try:
                processed = tuple(processor.process(raw))
                self._validate_processed(processed)
            except InvalidPayloadError as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.INVALID_PAYLOAD, str(exc)))
                continue
            except Exception as exc:
                attempts.append(self._attempt(reference, EvidenceStatus.PROCESSING_FAILED, str(exc)))
                continue
            evidence.extend(processed)
            attempt_status = (
                EvidenceStatus.EXTRACTION_FAILED
                if any(item.status == EvidenceStatus.EXTRACTION_FAILED for item in processed)
                else EvidenceStatus.SUCCESS
            )
            attempts.append(self._attempt(reference, attempt_status))

        comparisons = tuple(self.identity_validator.validate(listing, evidence))
        conflicts = tuple(item for item in comparisons if item.outcome == IdentityOutcome.CONFLICT)
        if conflicts:
            raise IdentityConflictError(conflicts)

        completion = self.policy.assess_completion(listing, evidence, attempts, comparisons)
        return self.assembler.assemble(
            listing,
            evidence,
            comparisons,
            attempts,
            completion,
            datetime.now(timezone.utc),
        )

    @staticmethod
    def _prepend_provenance(
        reference: EvidenceReference, prefix
    ) -> EvidenceReference:
        return replace(reference, provenance=tuple(prefix) + tuple(reference.provenance))

    @staticmethod
    def _attempt(
        reference: EvidenceReference,
        status: EvidenceStatus,
        message: str | None = None,
    ) -> EvidenceAttempt:
        return EvidenceAttempt(
            reference_identifier=reference.identifier,
            kind=reference.kind,
            retrieval_key=reference.retrieval_key,
            status=status,
            provenance=reference.provenance,
            message=message,
            locator=reference.locator,
        )

    @staticmethod
    def _validate_raw(raw: RawEvidence, reference: EvidenceReference) -> None:
        if raw.reference.retrieval_key != reference.retrieval_key:
            raise InvalidPayloadError("downloader returned evidence for a different retrieval key")
        if not isinstance(raw.payload, bytes) or not raw.payload:
            raise InvalidPayloadError("downloaded payload must contain non-empty bytes")

    @staticmethod
    def _validate_processed(processed: Sequence[Evidence]) -> None:
        if not processed:
            raise InvalidPayloadError("processor returned no evidence")
        allowed = {EvidenceStatus.SUCCESS, EvidenceStatus.EXTRACTION_FAILED}
        for item in processed:
            if item.status not in allowed:
                raise InvalidPayloadError(
                    "processors may only return successful evidence or retained extraction failures"
                )
            if not isinstance(item.payload, bytes) or not item.payload:
                raise InvalidPayloadError("processed evidence must preserve non-empty original bytes")
