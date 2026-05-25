#!/usr/bin/env python3
"""Compare web enrichment providers on fixture contacts (A/B spike harness).

Usage:
  uv run python scripts/enrichment_spike.py
  uv run python scripts/enrichment_spike.py --contacts path/to/contacts.json

Set EXA_API_KEY, TAVILY_API_KEY, and/or SERPER_API_KEY to include live provider calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from contactsafe_server.config import Settings
from contactsafe_server.services.exa_client import ExaClient
from contactsafe_server.services.person_discovery_service import PersonDiscoveryService
from contactsafe_server.services.serper_client import SerperClient
from contactsafe_server.services.tavily_client import TavilyClient
from contactsafe_server.services.web_enrichment import extract_hints_from_web_hits

DEFAULT_CONTACTS: list[dict[str, str]] = [
    {
        "name": "Jane Doe",
        "email": "jane@acmeventures.com",
        "org_hint": "Acme Ventures",
        "ground_truth_org": "Acme Ventures",
        "ground_truth_role": "General Partner",
    },
    {
        "name": "Alex Chen",
        "email": "alex@gmail.com",
        "org_hint": "",
        "ground_truth_org": "",
        "ground_truth_role": "Engineer",
    },
]


@dataclass(frozen=True, slots=True)
class ProviderSpikeResult:
    provider: str
    contact_name: str
    hit_count: int
    inferred_org: str | None
    inferred_role: str | None
    categories: list[str]
    social_profiles: list[str]
    cost_estimate_usd: float
    latency_ms: int | None = None


async def _timed_search(coro: object) -> tuple[object, int]:
    import time

    start: float = time.perf_counter()
    result: object = await coro  # type: ignore[misc]
    elapsed_ms: int = int((time.perf_counter() - start) * 1000)
    return result, elapsed_ms


async def run_spike(settings: Settings, contacts: list[dict[str, str]]) -> list[ProviderSpikeResult]:
    results: list[ProviderSpikeResult] = []
    discovery = PersonDiscoveryService(settings)
    exa = ExaClient(settings)
    tavily = TavilyClient(settings)
    serper = SerperClient(settings)

    cost_per_query: dict[str, float] = {
        "exa:people": 0.007,
        "exa:personal_site": 0.007,
        "tavily": 0.008,
        "serper": 0.001,
    }

    for contact in contacts:
        name: str = contact["name"]
        email: str = contact["email"]
        org_hint: str | None = contact.get("org_hint") or None

        provider_calls: list[tuple[str, object]] = []
        if settings.exa_api_key:
            provider_calls.extend(
                [
                    (
                        "exa:people",
                        exa.search_person_context(
                            name=name,
                            email=email,
                            org_hint=org_hint,
                            category="people",
                        ),
                    ),
                    (
                        "exa:personal_site",
                        exa.search_person_activity(name=name, org_hint=org_hint),
                    ),
                ]
            )
        if settings.tavily_api_key:
            provider_calls.extend(
                [
                    ("tavily", tavily.search_person_context(name=name, email=email, org_hint=org_hint)),
                    ("tavily:activity", tavily.search_person_activity(name=name, org_hint=org_hint)),
                ]
            )
        if settings.serper_api_key:
            provider_calls.extend(
                [
                    ("serper", serper.search_person_context(name=name, email=email, org_hint=org_hint)),
                    ("serper:activity", serper.search_person_activity(name=name, org_hint=org_hint)),
                ]
            )

        for provider, coro in provider_calls:
            try:
                hits_raw, latency_ms = await _timed_search(coro)
                hits = cast(list, hits_raw)
            except Exception as exc:
                results.append(
                    ProviderSpikeResult(
                        provider=f"{provider}:error",
                        contact_name=name,
                        hit_count=0,
                        inferred_org=None,
                        inferred_role=None,
                        categories=[],
                        social_profiles=[],
                        cost_estimate_usd=0.0,
                        latency_ms=None,
                    )
                )
                print(f"{provider} failed for {name}: {exc}")
                continue

            hints = extract_hints_from_web_hits(
                hits=hits,
                email=email,
                display_name=name,
                org_hint=org_hint,
            )
            results.append(
                ProviderSpikeResult(
                    provider=provider,
                    contact_name=name,
                    hit_count=len(hits),
                    inferred_org=hints.org_name,
                    inferred_role=hints.current_role,
                    categories=hints.categories,
                    social_profiles=sorted(hints.social_profiles.keys()),
                    cost_estimate_usd=cost_per_query.get(provider.split(":")[0], 0.008),
                    latency_ms=latency_ms,
                )
            )

        try:
            combined = await discovery.discover_person(name=name, email=email, org_hint=org_hint)
            activity_blob = discovery.activity_blob(combined)
            hints = extract_hints_from_web_hits(
                hits=combined.employer_hits,
                email=email,
                display_name=name,
                org_hint=org_hint,
                activity_posts=activity_blob,
            )
            results.append(
                ProviderSpikeResult(
                    provider="discovery_pipeline",
                    contact_name=name,
                    hit_count=len(combined.employer_hits) + len(combined.activity_hits),
                    inferred_org=hints.org_name,
                    inferred_role=hints.current_role,
                    categories=hints.categories,
                    social_profiles=sorted(hints.social_profiles.keys()),
                    cost_estimate_usd=sum(
                        cost_per_query.get(p.split(":")[0], 0.008)
                        for p in combined.providers_used
                    ),
                )
            )
        except Exception as exc:
            print(f"discovery pipeline failed for {name}: {exc}")

    return results


def _score_results(results: list[ProviderSpikeResult], contacts: list[dict[str, str]]) -> None:
    truth_by_name: dict[str, dict[str, str]] = {c["name"]: c for c in contacts}
    print("\n=== Spike summary ===")
    for result in results:
        truth = truth_by_name.get(result.contact_name, {})
        org_ok: bool = (
            not truth.get("ground_truth_org")
            or (result.inferred_org or "").lower() == truth["ground_truth_org"].lower()
        )
        role_ok: bool = (
            not truth.get("ground_truth_role")
            or (result.inferred_role or "").lower() == truth["ground_truth_role"].lower()
        )
        print(
            f"{result.provider:22} {result.contact_name:16} "
            f"hits={result.hit_count} org_ok={org_ok} role_ok={role_ok} "
            f"social={result.social_profiles} cost=${result.cost_estimate_usd:.4f} "
            f"latency={result.latency_ms}ms"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Web enrichment provider spike harness")
    parser.add_argument(
        "--contacts",
        type=Path,
        help="JSON file with [{name, email, org_hint, ground_truth_org, ground_truth_role}]",
    )
    args = parser.parse_args()

    contacts: list[dict[str, str]]
    if args.contacts and args.contacts.exists():
        contacts = cast(list[dict[str, str]], json.loads(args.contacts.read_text()))
    else:
        contacts = DEFAULT_CONTACTS

    settings = Settings()  # pyright: ignore[reportCallIssue]
    results = asyncio.run(run_spike(settings, contacts))
    print(json.dumps([asdict(r) for r in results], indent=2))
    _score_results(results, contacts)


if __name__ == "__main__":
    main()
