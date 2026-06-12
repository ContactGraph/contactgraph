"""Parse LinkedIn Connections.csv exports."""

from dataclasses import dataclass
import csv
from datetime import date, datetime
import io


@dataclass(frozen=True, slots=True)
class ParsedLinkedInConnection:
    first_name: str
    last_name: str
    email: str | None
    company: str | None
    position: str | None
    linkedin_url: str | None
    connected_on: date | None

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or "Unknown"


def _strip_linkedin_csv_preamble(content: str) -> str:
    """Skip LinkedIn's Notes preamble before the real CSV header."""
    lines: list[str] = content.splitlines()
    for index, line in enumerate(lines):
        normalized: str = line.strip().lower()
        if "first name" in normalized and "," in line:
            return "\n".join(lines[index:])
    return content


def _parse_connected_on(raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%d %b %Y").date()
    except ValueError:
        return None


def parse_linkedin_connections_csv(content: str) -> list[ParsedLinkedInConnection]:
    csv_content: str = _strip_linkedin_csv_preamble(content)
    reader = csv.DictReader(io.StringIO(csv_content))
    if reader.fieldnames is None:
        return []

    normalized_fields: dict[str, str] = {
        (name or "").strip().lower(): name or ""
        for name in reader.fieldnames
    }

    def field(*candidates: str) -> str | None:
        for candidate in candidates:
            key = candidate.lower()
            if key in normalized_fields:
                return normalized_fields[key]
        return None

    first_col: str | None = field("first name", "firstname")
    last_col: str | None = field("last name", "lastname")
    email_col: str | None = field("email address", "email")
    company_col: str | None = field("company", "organization")
    position_col: str | None = field("position", "title")
    url_col: str | None = field("url", "linkedin url", "profile url")
    connected_col: str | None = field("connected on", "connected")

    connections: list[ParsedLinkedInConnection] = []
    for row in reader:
        first: str = (row.get(first_col or "", "") or "").strip()
        last: str = (row.get(last_col or "", "") or "").strip()
        email_raw: str = (row.get(email_col or "", "") or "").strip().lower()
        company: str | None = (row.get(company_col or "", "") or "").strip() or None
        position: str | None = (row.get(position_col or "", "") or "").strip() or None
        url: str | None = (row.get(url_col or "", "") or "").strip() or None
        email: str | None = email_raw or None
        connected_on: date | None = _parse_connected_on(row.get(connected_col or "", ""))
        if not first and not last and not email and not url:
            continue
        connections.append(
            ParsedLinkedInConnection(
                first_name=first,
                last_name=last,
                email=email,
                company=company,
                position=position,
                linkedin_url=url,
                connected_on=connected_on,
            )
        )
    return connections
