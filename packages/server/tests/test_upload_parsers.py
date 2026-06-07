from datetime import date

from contactsafe_server.services.linkedin_connections_parser import (
    parse_linkedin_connections_csv,
)
from contactsafe_server.services.phone_contacts_parser import parse_phone_contacts_upload


def test_parse_phone_contacts_vcard() -> None:
    content = """BEGIN:VCARD
FN:Jane Doe
EMAIL:jane@example.com
TEL:+1-555-0100
END:VCARD
"""
    contacts = parse_phone_contacts_upload(content, "contacts.vcf")
    assert len(contacts) == 1
    assert contacts[0].display_name == "Jane Doe"
    assert contacts[0].email == "jane@example.com"
    assert contacts[0].phone == "+1-555-0100"


def test_parse_phone_contacts_vcard_org_and_linkedin() -> None:
    content = """BEGIN:VCARD
FN:Ada Lovelace
EMAIL:ada@example.com
TEL:+1-555-0101
ORG:Analytical Engines
TITLE:Engineer
URL:https://www.linkedin.com/in/ada
END:VCARD
"""
    contacts = parse_phone_contacts_upload(content, "contacts.vcf")
    assert len(contacts) == 1
    assert contacts[0].org_name == "Analytical Engines"
    assert contacts[0].org_title == "Engineer"
    assert contacts[0].linkedin_url == "https://www.linkedin.com/in/ada"


def test_parse_linkedin_connections_csv() -> None:
    content = """First Name,Last Name,Email Address,Company,Position,URL
Ada,Lovelace,ada@example.com,Analytical Engines,Engineer,https://linkedin.com/in/ada
"""
    rows = parse_linkedin_connections_csv(content)
    assert len(rows) == 1
    assert rows[0].display_name == "Ada Lovelace"
    assert rows[0].email == "ada@example.com"
    assert rows[0].company == "Analytical Engines"
    assert rows[0].connected_on is None


def test_parse_linkedin_connections_csv_with_notes_preamble() -> None:
    content = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Zeev,Neumeier,https://www.linkedin.com/in/zeev-neumeier,,Gray Swan,Founder,30 Apr 2026
"""
    rows = parse_linkedin_connections_csv(content)
    assert len(rows) == 1
    assert rows[0].display_name == "Zeev Neumeier"
    assert rows[0].linkedin_url == "https://www.linkedin.com/in/zeev-neumeier"
    assert rows[0].company == "Gray Swan"
    assert rows[0].connected_on == date(2026, 4, 30)


def test_parse_linkedin_connections_csv_skips_ghost_rows() -> None:
    content = """First Name,Last Name,URL,Email Address,Company,Position,Connected On
Ada,Lovelace,https://www.linkedin.com/in/ada,ada@example.com,Analytical Engines,Engineer,01 Jan 2024
,,,,,,19 Jan 2024
"""
    rows = parse_linkedin_connections_csv(content)
    assert len(rows) == 1
    assert rows[0].display_name == "Ada Lovelace"
    assert rows[0].connected_on == date(2024, 1, 1)


def test_parse_linkedin_connections_csv_connected_on() -> None:
    content = """First Name,Last Name,URL,Email Address,Company,Position,Connected On
Tim,Williamson,https://www.linkedin.com/in/timhwilliamson,,NieuxCo,CEO,30 Apr 2026
"""
    rows = parse_linkedin_connections_csv(content)
    assert len(rows) == 1
    assert rows[0].connected_on == date(2026, 4, 30)
