from contactsafe_server.services.org_funding_stage import (
    FUNDING_STAGE_ORDER,
    funding_stage_label,
    normalize_funding_stage,
)


def test_normalize_funding_stage_canonical() -> None:
    assert normalize_funding_stage("seed") == "seed"
    assert normalize_funding_stage("series_a") == "series_a"
    assert normalize_funding_stage("series_b") == "series_b"
    assert normalize_funding_stage("series_c_plus") == "series_c_plus"
    assert normalize_funding_stage("mezzanine") == "mezzanine"
    assert normalize_funding_stage("public") == "public"
    assert normalize_funding_stage("mature") == "mature"
    assert normalize_funding_stage("unknown") == "unknown"


def test_normalize_funding_stage_aliases() -> None:
    assert normalize_funding_stage("Series A") == "series_a"
    assert normalize_funding_stage("seriesA") == "series_a"
    assert normalize_funding_stage("series-a") == "series_a"
    assert normalize_funding_stage("Series C+") == "series_c_plus"
    assert normalize_funding_stage("Series D") == "series_c_plus"
    assert normalize_funding_stage("IPO") == "public"
    assert normalize_funding_stage("publicly traded") == "public"
    assert normalize_funding_stage("bootstrapped") == "mature"
    assert normalize_funding_stage("pre-seed") == "seed"
    assert normalize_funding_stage("pre-ipo") == "mezzanine"


def test_normalize_funding_stage_rejects_unknown() -> None:
    assert normalize_funding_stage(None) is None
    assert normalize_funding_stage("") is None
    assert normalize_funding_stage("   ") is None
    assert normalize_funding_stage("not-a-stage") is None


def test_funding_stage_label() -> None:
    assert funding_stage_label("series_b") == "Series B"
    assert funding_stage_label(None) == "—"
    assert funding_stage_label("unknown") == "Unknown"


def test_funding_stage_order_covers_taxonomy() -> None:
    assert set(FUNDING_STAGE_ORDER) == {
        "seed",
        "series_a",
        "series_b",
        "series_c_plus",
        "mezzanine",
        "public",
        "mature",
        "unknown",
    }
