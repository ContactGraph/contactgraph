"""Backward-compatible re-exports for Exa enrichment helpers."""

from contactsafe_server.services.web_enrichment import (
    ExaPersonHints,
    PersonWebHints,
    apply_exa_hints_to_person,
    apply_web_hints_to_person,
    extract_hints_from_exa_hits,
    extract_hints_from_web_hits,
)

__all__ = [
    "ExaPersonHints",
    "PersonWebHints",
    "apply_exa_hints_to_person",
    "apply_web_hints_to_person",
    "extract_hints_from_exa_hits",
    "extract_hints_from_web_hits",
]
