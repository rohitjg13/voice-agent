"""CSV lead import: normalization, aliasing, dupes, DNC, row caps."""

from uuid import uuid4

import pytest

from orchestrator import db
from orchestrator.services.lead_import import import_leads, normalize_phone
from tests.fakes import FakeDB

ORG_ID = uuid4()
CAMPAIGN_ID = uuid4()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("555-123-4567", "+15551234567"),
        ("(415) 555 0100", "+14155550100"),
        ("+44 20 7946 0958", "+442079460958"),
        ("14155550100", "+14155550100"),
        ("00442079460958", "+442079460958"),
        ("12345", None),
        ("not a phone", None),
        ("", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.fixture
def fake_db():
    fdb = FakeDB({"INSERT INTO leads": "INSERT 0 1"})
    db.set_pool(fdb)
    yield fdb
    db.set_pool(None)


async def test_import_with_aliased_headers(fake_db):
    csv_bytes = (
        b"Full Name,Company,Phone Number,Email\n"
        b"Jane Doe,Acme Dental,415-555-0100,jane@acme.com\n"
        b"John Roe,Roe DDS,415-555-0101,\n"
    )
    report = await import_leads(ORG_ID, CAMPAIGN_ID, csv_bytes)
    assert report == {"imported": 2, "skipped": []}
    inserts = fake_db.queries("INSERT INTO leads")
    assert inserts[0][1][2] == "Jane Doe"
    assert inserts[0][1][5] == "+14155550100"


async def test_import_skips_bad_rows_with_reasons(fake_db):
    csv_bytes = (
        b"name,phone\n"
        b"Good,415-555-0100\n"
        b"Bad,12\n"
        b"Dupe,415-555-0100\n"
        b"Blocked,+15551234567\n"  # on the DNC test blocklist
    )
    report = await import_leads(ORG_ID, CAMPAIGN_ID, csv_bytes)
    assert report["imported"] == 1
    reasons = {s["row"]: s["reason"] for s in report["skipped"]}
    assert reasons == {
        3: "invalid phone",
        4: "duplicate in file",
        5: "do-not-call list",
    }


async def test_import_skips_db_duplicates(fake_db):
    fake_db.responses["INSERT INTO leads"] = "INSERT 0 0"
    report = await import_leads(ORG_ID, CAMPAIGN_ID, b"phone\n4155550100\n")
    assert report["imported"] == 0
    assert report["skipped"][0]["reason"] == "already in campaign"


async def test_import_respects_row_cap(fake_db):
    csv_bytes = b"phone\n4155550100\n4155550101\n4155550102\n"
    report = await import_leads(ORG_ID, CAMPAIGN_ID, csv_bytes, max_rows=2)
    assert report["imported"] == 2
    assert report["skipped"][0]["reason"] == "over row limit"


async def test_import_without_phone_column(fake_db):
    report = await import_leads(ORG_ID, CAMPAIGN_ID, b"name,email\nJane,j@x.com\n")
    assert report["imported"] == 0
    assert report["skipped"][0]["reason"] == "no phone column found"
