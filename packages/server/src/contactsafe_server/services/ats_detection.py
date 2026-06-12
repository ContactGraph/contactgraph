"""Detect ATS provider and board token from organization careers URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from contactsafe_server.db.models import Org

AtsProvider = Literal["greenhouse", "lever", "ashby"]

_GREENHOUSE_HOST_RE: re.Pattern[str] = re.compile(
    r"^(?:boards|job-boards)\.greenhouse\.io$",
    flags=re.IGNORECASE,
)
_GREENHOUSE_PATH_RE: re.Pattern[str] = re.compile(
    r"^/([^/?#]+)",
    flags=re.IGNORECASE,
)
_LEVER_HOST_RE: re.Pattern[str] = re.compile(
    r"^jobs\.lever\.co$",
    flags=re.IGNORECASE,
)
_ASHBY_HOST_RE: re.Pattern[str] = re.compile(
    r"^jobs\.ashbyhq\.com$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AtsDetectionResult:
    provider: AtsProvider | None
    board_token: str | None


def detect_ats_from_url(careers_url: str) -> AtsDetectionResult:
    normalized: str = careers_url.strip()
    if not normalized:
        return AtsDetectionResult(provider=None, board_token=None)

    parsed = urlparse(normalized)
    host: str = (parsed.hostname or "").lower()
    if not host:
        return AtsDetectionResult(provider=None, board_token=None)

    path_match: re.Match[str] | None = _GREENHOUSE_PATH_RE.match(parsed.path or "")
    slug: str | None = path_match.group(1) if path_match is not None else None
    if slug and _GREENHOUSE_HOST_RE.match(host):
        return AtsDetectionResult(provider="greenhouse", board_token=slug)

    if slug and _LEVER_HOST_RE.match(host):
        return AtsDetectionResult(provider="lever", board_token=slug)

    if slug and _ASHBY_HOST_RE.match(host):
        return AtsDetectionResult(provider="ashby", board_token=slug)

    return AtsDetectionResult(provider=None, board_token=None)


def apply_ats_detection_to_org(org: Org) -> None:
    if org.careers_url is None or not org.careers_url.strip():
        org.ats_provider = None
        org.ats_board_token = None
        return
    result: AtsDetectionResult = detect_ats_from_url(org.careers_url)
    org.ats_provider = result.provider
    org.ats_board_token = result.board_token
