"""Classify email contacts as human, broadcast, or automated senders."""

from dataclasses import dataclass
import re

from contactsafe_server.services.email_parse import (
    NO_REPLY_LOCAL_PARTS,
    ContactAccumulator,
    is_human_edge,
    is_likely_broadcast_contact,
)
from contactsafe_server.services.org_search import is_automation_domain

_AUTOMATED_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "ci_activity",
        "ci",
        "subscribed",
        "push",
        "pull",
        "issues",
        "commits",
        "actions",
        "security",
        "dependabot",
    }
)

_AUTOMATED_LOCAL_PREFIXES: tuple[str, ...] = (
    "failed-payments",
    "noreply+",
    "no-reply+",
)


@dataclass(frozen=True, slots=True)
class ContactClassification:
    is_automated: bool
    is_broadcast: bool
    is_human: bool


def classify_contact(accumulator: ContactAccumulator) -> ContactClassification:
    """Return contact kind flags used for tie strength, enrichment, and queries."""
    is_automated: bool = _is_automated_contact(accumulator)
    is_broadcast: bool = (
        not is_automated and _is_broadcast_contact(accumulator)
    ) or (is_automated and _is_marketing_automation(accumulator))
    is_human: bool = (
        not is_automated
        and not is_broadcast
        and is_human_edge(accumulator)
    )
    return ContactClassification(
        is_automated=is_automated,
        is_broadcast=is_broadcast,
        is_human=is_human,
    )


def compute_tie_strength(
    accumulator: ContactAccumulator,
    classification: ContactClassification,
) -> float:
    """Score relationship strength; penalize automated and broadcast contacts."""
    base: float = min(1.0, float(accumulator.message_count) / 20.0)
    if classification.is_automated:
        base *= 0.05
    elif classification.is_broadcast:
        base *= 0.1
    elif not classification.is_human:
        base *= 0.5

    if classification.is_human:
        mutual: int = min(accumulator.outbound_count, accumulator.inbound_count)
        base = min(1.0, base + min(0.3, float(mutual) / 10.0))

    return round(base, 4)


def _is_automated_contact(accumulator: ContactAccumulator) -> bool:
    local, domain = accumulator.email.rsplit("@", 1)
    local_lower: str = local.lower()
    domain_lower: str = domain.lower()

    if is_automation_domain(domain_lower):
        return True

    if local_lower in _AUTOMATED_LOCAL_PARTS:
        return True
    if any(local_lower.startswith(prefix) for prefix in _AUTOMATED_LOCAL_PREFIXES):
        return True
    if re.search(r"\+acct_", local_lower):
        return True
    if "noreply" in domain_lower:
        return True

    return False


def _is_broadcast_contact(accumulator: ContactAccumulator) -> bool:
    if is_likely_broadcast_contact(accumulator):
        return True
    _local, domain = accumulator.email.rsplit("@", 1)
    domain_lower: str = domain.lower()
    if domain_lower.startswith("e.") or ".ccsend.com" in domain_lower:
        return True
    if domain_lower.startswith(("email.", "mail.", "notify.", "notification.", "marketing.")):
        return True
    return False


def _is_marketing_automation(accumulator: ContactAccumulator) -> bool:
    """One-way marketing senders that are not generic noreply bots."""
    return (
        accumulator.outbound_count == 0
        and accumulator.inbound_count >= 3
    )
