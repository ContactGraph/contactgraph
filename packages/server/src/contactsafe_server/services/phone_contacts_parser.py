"""Parse phone contact uploads (vCard or CSV)."""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass

import vobject

logger: logging.Logger = logging.getLogger(__name__)

_LINKEDIN_URL_RE: re.Pattern[str] = re.compile(
    r"linkedin\.com/in/", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class ParsedPhoneContact:
    display_name: str
    emails: tuple[str, ...] = ()
    phone_numbers: tuple[str, ...] = ()
    org_name: str | None = None
    org_title: str | None = None
    urls: tuple[str, ...] = ()
    address: str | None = None

    @property
    def email(self) -> str | None:
        return self.emails[0] if self.emails else None

    @property
    def phone(self) -> str | None:
        return self.phone_numbers[0] if self.phone_numbers else None

    @property
    def linkedin_url(self) -> str | None:
        for url in self.urls:
            if _LINKEDIN_URL_RE.search(url):
                return url.rstrip("/")
        return None


def parse_phone_contacts_upload(content: str, filename: str) -> list[ParsedPhoneContact]:
    lowered: str = filename.lower()
    if lowered.endswith(".vcf") or lowered.endswith(".vcard") or "BEGIN:VCARD" in content:
        return _parse_vcard(content)
    return _parse_csv(content)


def _parse_vcard(content: str) -> list[ParsedPhoneContact]:
    contacts: list[ParsedPhoneContact] = []
    for component in vobject.readComponents(content):
        if component.name.upper() != "VCARD":
            continue
        try:
            parsed: ParsedPhoneContact | None = _vcard_to_contact(component)
            if parsed is not None:
                contacts.append(parsed)
        except Exception:
            logger.debug("Skipping malformed vCard entry", exc_info=True)
    return contacts


def _vcard_to_contact(component: vobject.base.Component) -> ParsedPhoneContact | None:
    display_name: str = _vcard_display_name(component)
    emails: list[str] = _vcard_emails(component)
    phones: list[str] = _vcard_phones(component)
    org_name: str | None = _vcard_org_name(component)
    org_title: str | None = _vcard_org_title(component)
    urls: list[str] = _vcard_urls(component)
    address: str | None = _vcard_address(component)

    if not display_name and not emails and not phones:
        return None
    if not display_name:
        display_name = emails[0] if emails else (phones[0] if phones else "Unknown")

    return ParsedPhoneContact(
        display_name=display_name,
        emails=tuple(emails),
        phone_numbers=tuple(phones),
        org_name=org_name,
        org_title=org_title,
        urls=tuple(urls),
        address=address,
    )


def _vcard_display_name(component: vobject.base.Component) -> str:
    if hasattr(component, "fn"):
        value: str = str(component.fn.value).strip()
        if value:
            return value
    if hasattr(component, "n"):
        parts: list[str] = [str(part).strip() for part in component.n.value]
        family: str = parts[0] if parts else ""
        given: str = parts[1] if len(parts) > 1 else ""
        combined: str = f"{given} {family}".strip()
        if combined:
            return combined
    return ""


def _vcard_emails(component: vobject.base.Component) -> list[str]:
    emails: list[str] = []
    if hasattr(component, "email_list"):
        for entry in component.email_list:
            normalized: str = str(entry.value).strip().lower()
            if normalized and normalized not in emails:
                emails.append(normalized)
    elif hasattr(component, "email"):
        normalized = str(component.email.value).strip().lower()
        if normalized:
            emails.append(normalized)
    return emails


def _vcard_phones(component: vobject.base.Component) -> list[str]:
    phones: list[str] = []
    if hasattr(component, "tel_list"):
        for entry in component.tel_list:
            normalized: str = str(entry.value).strip()
            if normalized and normalized not in phones:
                phones.append(normalized)
    elif hasattr(component, "tel"):
        normalized = str(component.tel.value).strip()
        if normalized:
            phones.append(normalized)
    return phones


def _vcard_org_name(component: vobject.base.Component) -> str | None:
    if not hasattr(component, "org"):
        return None
    org_value = component.org.value
    if isinstance(org_value, list):
        parts: list[str] = [str(part).strip() for part in org_value if str(part).strip()]
        return parts[0] if parts else None
    org_text: str = str(org_value).strip()
    return org_text or None


def _vcard_org_title(component: vobject.base.Component) -> str | None:
    if not hasattr(component, "title"):
        return None
    title: str = str(component.title.value).strip()
    return title or None


def _vcard_urls(component: vobject.base.Component) -> list[str]:
    urls: list[str] = []
    if hasattr(component, "url_list"):
        for entry in component.url_list:
            normalized: str = str(entry.value).strip()
            if normalized and normalized not in urls:
                urls.append(normalized)
    elif hasattr(component, "url"):
        normalized = str(component.url.value).strip()
        if normalized:
            urls.append(normalized)
    return urls


def _vcard_address(component: vobject.base.Component) -> str | None:
    if not hasattr(component, "adr"):
        return None
    adr_value = component.adr.value
    if isinstance(adr_value, list):
        parts: list[str] = [str(part).strip() for part in adr_value if str(part).strip()]
        combined: str = ", ".join(parts)
        return combined or None
    text: str = str(adr_value).strip()
    return text or None


def _parse_csv(content: str) -> list[ParsedPhoneContact]:
    reader = csv.DictReader(io.StringIO(content))
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

    name_col: str | None = field("name", "display name", "full name")
    email_col: str | None = field("email", "e-mail", "email address")
    phone_col: str | None = field("phone", "mobile", "telephone", "phone number")

    contacts: list[ParsedPhoneContact] = []
    for row in reader:
        display_name: str = (row.get(name_col or "", "") or "").strip()
        email_raw: str = (row.get(email_col or "", "") or "").strip().lower()
        phone_raw: str = (row.get(phone_col or "", "") or "").strip()
        emails: tuple[str, ...] = (email_raw,) if email_raw else ()
        phones: tuple[str, ...] = (phone_raw,) if phone_raw else ()
        if not display_name and not emails and not phones:
            continue
        if not display_name:
            display_name = email_raw or phone_raw or "Unknown"
        contacts.append(
            ParsedPhoneContact(
                display_name=display_name,
                emails=emails,
                phone_numbers=phones,
            )
        )
    return contacts
