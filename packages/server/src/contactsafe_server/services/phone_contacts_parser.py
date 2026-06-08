"""Parse phone contact uploads (vCard or CSV)."""

from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import vobject

_FieldLookup = Callable[..., str | None]

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

    if not display_name:
        return None

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
        n_value = component.n.value
        if hasattr(n_value, "given") and hasattr(n_value, "family"):
            given: str = str(n_value.given).strip()
            family: str = str(n_value.family).strip()
        elif isinstance(n_value, (list, tuple)):
            family = str(n_value[0]).strip() if n_value else ""
            given = str(n_value[1]).strip() if len(n_value) > 1 else ""
        else:
            return str(n_value).strip()
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

    is_google_csv: bool = field("given name") is not None

    if is_google_csv:
        return _parse_google_csv(reader, field)

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
        if not display_name:
            continue
        contacts.append(
            ParsedPhoneContact(
                display_name=display_name,
                emails=emails,
                phone_numbers=phones,
            )
        )
    return contacts


def _parse_google_csv(
    reader: csv.DictReader[str],
    field: _FieldLookup,
) -> list[ParsedPhoneContact]:
    """Parse Google Contacts CSV export format.

    Google CSV uses structured column names like 'Given Name', 'Family Name',
    'Phone 1 - Value', 'E-mail 1 - Value', etc.
    """
    given_col: str | None = field("given name")
    family_col: str | None = field("family name")
    name_col: str | None = field("name", "display name", "full name")
    org_col: str | None = field("organization 1 - name")
    title_col: str | None = field("organization 1 - title")

    all_fields: set[str] = set(reader.fieldnames or [])
    email_cols: list[str] = sorted(
        col for col in all_fields
        if col.lower().startswith("e-mail") and col.lower().endswith("- value")
    )
    phone_cols: list[str] = sorted(
        col for col in all_fields
        if col.lower().startswith("phone") and col.lower().endswith("- value")
    )

    contacts: list[ParsedPhoneContact] = []
    for row in reader:
        given: str = (row.get(given_col or "", "") or "").strip()
        family: str = (row.get(family_col or "", "") or "").strip()
        display_name: str = f"{given} {family}".strip()
        if not display_name and name_col:
            display_name = (row.get(name_col, "") or "").strip()
        if not display_name:
            continue

        emails: list[str] = []
        for col in email_cols:
            val: str = (row.get(col, "") or "").strip().lower()
            if val and val not in emails:
                emails.append(val)

        phones: list[str] = []
        for col in phone_cols:
            val = (row.get(col, "") or "").strip()
            if val and val not in phones:
                phones.append(val)

        org_name: str | None = (row.get(org_col or "", "") or "").strip() or None
        org_title: str | None = (row.get(title_col or "", "") or "").strip() or None

        contacts.append(
            ParsedPhoneContact(
                display_name=display_name,
                emails=tuple(emails),
                phone_numbers=tuple(phones),
                org_name=org_name,
                org_title=org_title,
            )
        )
    return contacts
