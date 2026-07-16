"""Parse a LinkedIn profile PDF (Save to PDF) into structured data.

Uses pypdf to extract text, then an LLM (if available) or heuristic
section-splitting to produce structured experience/education data.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import httpx
from pypdf import PdfReader

from contactsafe_server.config import Settings
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object

logger: logging.Logger = logging.getLogger(__name__)

_SECTION_HEADINGS: re.Pattern[str] = re.compile(
    r"^(Experience|Education|Skills|About|Summary|Languages|"
    r"Certifications|Licenses & Certifications|Honors & Awards|"
    r"Projects|Publications|Volunteer Experience|Contact)$",
    flags=re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class ParsedExperience:
    company: str
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedEducation:
    school: str
    degree: str | None = None
    field_of_study: str | None = None
    start_year: int | None = None
    end_year: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedLinkedInProfile:
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    about: str | None = None
    experiences: list[ParsedExperience] = field(default_factory=list)
    education: list[ParsedEducation] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    raw_text: str = ""


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text: str | None = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _parse_month_year(text: str) -> date | None:
    """Parse strings like 'Jan 2020', 'January 2020', '2020'."""
    text = text.strip()
    month_map: dict[str, int] = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }
    parts: list[str] = text.lower().split()
    if len(parts) == 2:
        month_str: str = parts[0]
        year_str: str = parts[1]
        month: int | None = month_map.get(month_str)
        if month is not None and year_str.isdigit():
            return date(int(year_str), month, 1)
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) == 4:
        return date(int(parts[0]), 1, 1)
    return None


def _split_sections(text: str) -> dict[str, str]:
    """Split PDF text into named sections by LinkedIn headings."""
    sections: dict[str, str] = {}
    positions: list[tuple[int, str]] = []
    for match in _SECTION_HEADINGS.finditer(text):
        positions.append((match.start(), match.group(1)))

    if not positions:
        return {"_raw": text}

    header_text: str = text[: positions[0][0]].strip()
    if header_text:
        sections["_header"] = header_text

    for i, (pos, heading) in enumerate(positions):
        next_pos: int = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content: str = text[pos + len(heading) : next_pos].strip()
        sections[heading] = content

    return sections


def _parse_header(header: str) -> tuple[str | None, str | None, str | None]:
    """Extract name, headline, location from the header block."""
    lines: list[str] = [line.strip() for line in header.strip().splitlines() if line.strip()]
    name: str | None = lines[0] if lines else None
    headline: str | None = lines[1] if len(lines) > 1 else None
    location: str | None = None
    for line in lines[2:]:
        if any(kw in line.lower() for kw in [",", "area", "region", "city", "metro"]):
            location = line
            break
    return name, headline, location


_DATE_RANGE_RE: re.Pattern[str] = re.compile(
    r"(\w+\s+\d{4}|\d{4})\s*[-–]\s*(Present|\w+\s+\d{4}|\d{4})",
    flags=re.IGNORECASE,
)


_EMPLOYMENT_TYPE_RE: re.Pattern[str] = re.compile(
    r"\b(full-time|part-time|self-employed|contract|internship|freelance)\b",
    flags=re.IGNORECASE,
)


def _strip_employment_type(line: str) -> str:
    return line.split("·", maxsplit=1)[0].strip()


def _heuristic_parse_experiences(text: str) -> list[ParsedExperience]:
    """Best-effort parsing of the Experience section."""
    experiences: list[ParsedExperience] = []
    blocks: list[str] = re.split(r"\n{2,}", text)

    for block in blocks:
        lines: list[str] = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue

        title: str | None = None
        company: str | None = None
        start: date | None = None
        end: date | None = None
        is_current: bool = False
        loc: str | None = None

        if len(lines) >= 2:
            first_line: str = lines[0]
            second_line: str = lines[1]
            company_first: bool = (
                "·" in first_line
                and _EMPLOYMENT_TYPE_RE.search(first_line) is not None
            )

            if company_first:
                company = _strip_employment_type(first_line)
                title = second_line.split("·", maxsplit=1)[0].strip()
            else:
                title = first_line
                company = second_line
        elif len(lines) == 1:
            company = lines[0]

        date_match: re.Match[str] | None = _DATE_RANGE_RE.search(block)
        if date_match:
            start = _parse_month_year(date_match.group(1))
            if date_match.group(2).lower() == "present":
                is_current = True
            else:
                end = _parse_month_year(date_match.group(2))

        for line in lines[2:]:
            if "," in line and len(line) < 60 and not _DATE_RANGE_RE.search(line):
                loc = line
                break

        if company:
            experiences.append(ParsedExperience(
                company=company,
                title=title,
                start_date=start,
                end_date=end,
                is_current=is_current,
                location=loc,
            ))

    return experiences


def _heuristic_parse_education(text: str) -> list[ParsedEducation]:
    blocks: list[str] = re.split(r"\n{2,}", text)
    education: list[ParsedEducation] = []
    for block in blocks:
        lines: list[str] = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        school: str = lines[0]
        degree: str | None = None
        field_of_study: str | None = None
        start_year: int | None = None
        end_year: int | None = None

        for line in lines[1:]:
            if "," in line and degree is None:
                parts: list[str] = line.split(",", 1)
                degree = parts[0].strip()
                field_of_study = parts[1].strip() if len(parts) > 1 else None
            elif degree is None and not line[0].isdigit():
                degree = line

        year_matches: list[str] = re.findall(r"\b(19|20)\d{2}\b", block)
        if len(year_matches) >= 2:
            start_year = int(year_matches[0])
            end_year = int(year_matches[1])
        elif len(year_matches) == 1:
            end_year = int(year_matches[0])

        education.append(ParsedEducation(
            school=school,
            degree=degree,
            field_of_study=field_of_study,
            start_year=start_year,
            end_year=end_year,
        ))
    return education


def _heuristic_parse(text: str) -> ParsedLinkedInProfile:
    sections: dict[str, str] = _split_sections(text)
    name: str | None = None
    headline: str | None = None
    location: str | None = None

    if "_header" in sections:
        name, headline, location = _parse_header(sections["_header"])

    about: str | None = sections.get("About") or sections.get("Summary")

    experiences: list[ParsedExperience] = []
    if "Experience" in sections:
        experiences = _heuristic_parse_experiences(sections["Experience"])

    education: list[ParsedEducation] = []
    if "Education" in sections:
        education = _heuristic_parse_education(sections["Education"])

    skills: list[str] = []
    if "Skills" in sections:
        skills = [
            s.strip()
            for s in re.split(r"[·•\n]", sections["Skills"])
            if s.strip() and len(s.strip()) < 80
        ]

    return ParsedLinkedInProfile(
        name=name,
        headline=headline,
        location=location,
        about=about,
        experiences=experiences,
        education=education,
        skills=skills,
        raw_text=text,
    )


_LLM_SYSTEM_PROMPT: str = """\
You are a resume parser. Extract structured data from a LinkedIn profile PDF.
Return a JSON object with these fields:
- "name": string or null
- "headline": string or null (e.g. "VP Engineering at Stripe")
- "location": string or null
- "about": string or null (summary/about section)
- "experiences": array of objects with:
  - "company": string (required)
  - "title": string or null
  - "start_date": string "YYYY-MM-DD" or null (use first of month if only month/year)
  - "end_date": string "YYYY-MM-DD" or null
  - "is_current": boolean
  - "location": string or null
- "education": array of objects with:
  - "school": string (required)
  - "degree": string or null
  - "field_of_study": string or null
  - "start_year": integer or null
  - "end_year": integer or null
- "skills": array of strings

Return ONLY valid JSON, no markdown fencing."""


def _parse_date_str(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return _parse_month_year(value)


def _llm_result_to_profile(data: dict[str, object], raw_text: str) -> ParsedLinkedInProfile:
    experiences: list[ParsedExperience] = []
    raw_exp: object = data.get("experiences")
    if isinstance(raw_exp, list):
        for item in raw_exp:
            if not isinstance(item, dict):
                continue
            company: object = item.get("company")
            if not isinstance(company, str) or not company.strip():
                continue
            experiences.append(ParsedExperience(
                company=company.strip(),
                title=item.get("title") if isinstance(item.get("title"), str) else None,
                start_date=_parse_date_str(item.get("start_date")),
                end_date=_parse_date_str(item.get("end_date")),
                is_current=bool(item.get("is_current")),
                location=item.get("location") if isinstance(item.get("location"), str) else None,
            ))

    education: list[ParsedEducation] = []
    raw_edu: object = data.get("education")
    if isinstance(raw_edu, list):
        for item in raw_edu:
            if not isinstance(item, dict):
                continue
            school: object = item.get("school")
            if not isinstance(school, str) or not school.strip():
                continue
            start_yr: object = item.get("start_year")
            end_yr: object = item.get("end_year")
            education.append(ParsedEducation(
                school=school.strip(),
                degree=item.get("degree") if isinstance(item.get("degree"), str) else None,
                field_of_study=item.get("field_of_study") if isinstance(item.get("field_of_study"), str) else None,
                start_year=int(start_yr) if isinstance(start_yr, (int, float)) else None,
                end_year=int(end_yr) if isinstance(end_yr, (int, float)) else None,
            ))

    raw_skills: object = data.get("skills")
    skills: list[str] = []
    if isinstance(raw_skills, list):
        for s in raw_skills:
            if isinstance(s, str) and s.strip():
                skills.append(s.strip())

    name: object = data.get("name")
    headline: object = data.get("headline")
    location: object = data.get("location")
    about: object = data.get("about")

    return ParsedLinkedInProfile(
        name=name if isinstance(name, str) else None,
        headline=headline if isinstance(headline, str) else None,
        location=location if isinstance(location, str) else None,
        about=about if isinstance(about, str) else None,
        experiences=experiences,
        education=education,
        skills=skills,
        raw_text=raw_text,
    )


async def _llm_parse(text: str, settings: Settings) -> ParsedLinkedInProfile | None:
    if not settings.openai_api_key:
        return None

    truncated: str = text[:12000]
    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_enrichment_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": truncated},
                    ],
                },
            )
            response.raise_for_status()
            data: dict[str, object] = parse_json_object(
                content_from_chat_completion(json.loads(response.text))
            )
            return _llm_result_to_profile(data, text)
    except Exception:
        logger.exception("LLM LinkedIn profile parsing failed, falling back to heuristic")
        return None


async def parse_linkedin_profile_pdf(
    content_base64: str,
    settings: Settings,
) -> ParsedLinkedInProfile:
    """Parse a base64-encoded LinkedIn profile PDF."""
    pdf_bytes: bytes = base64.b64decode(content_base64)
    raw_text: str = _extract_text_from_pdf(pdf_bytes)

    if not raw_text.strip():
        return ParsedLinkedInProfile(raw_text="")

    llm_result: ParsedLinkedInProfile | None = await _llm_parse(raw_text, settings)
    if llm_result is not None:
        return llm_result

    return _heuristic_parse(raw_text)
