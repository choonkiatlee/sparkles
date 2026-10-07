"""Typed errors raised by the retrieval framework."""
from __future__ import annotations

from .models import IdentityComparison


class DiamondRetrievalError(Exception):
    """Base class for public retrieval errors."""


class ConfigurationError(DiamondRetrievalError):
    """Invalid or ambiguous component configuration."""


class AmbiguousRegistrationError(ConfigurationError):
    """More than one registered component claims the same input."""


class UnsupportedInputError(DiamondRetrievalError):
    """No listing provider supports the supplied input URL."""


class RetrievalError(DiamondRetrievalError):
    """The listing itself could not establish a retrievable diamond."""


class EvidenceAccessError(Exception):
    """Base class for adapter failures that become structured attempts."""


class MissingEvidenceError(EvidenceAccessError):
    """A referenced evidence asset is absent."""


class UnsupportedEvidenceError(EvidenceAccessError):
    """A component recognizes a reference but cannot retrieve its format."""


class InvalidPayloadError(EvidenceAccessError):
    """Downloaded bytes fail mandatory generic validation."""


class IdentityConflictError(DiamondRetrievalError):
    """Comparable identity observations disagree."""

    def __init__(self, comparisons: tuple[IdentityComparison, ...]):
        self.comparisons = comparisons
        fields = ", ".join(item.field for item in comparisons)
        super().__init__(f"Conflicting diamond identity observations: {fields}")
