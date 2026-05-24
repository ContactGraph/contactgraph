from contactsafe_core.query_plan import QueryIntent
from contactsafe_server.services.heuristic_query_planner import plan_from_heuristics


def test_heuristic_name_query() -> None:
    plan = plan_from_heuristics("Who do I know named Chris?")
    assert "chris" in plan.name_tokens
    assert plan.exclude_broadcast is True


def test_heuristic_vc_categories() -> None:
    plan = plan_from_heuristics("What VCs do I know?")
    assert "vc" in plan.categories_any


def test_heuristic_org_and_lookup() -> None:
    plan = plan_from_heuristics("What is the email for Chris at AIX?")
    assert plan.intent == QueryIntent.LOOKUP_CONTACT
    assert "chris" in plan.name_tokens
    assert any("aix" in org.lower() for org in plan.org_names)


def test_heuristic_semantic_intent() -> None:
    plan = plan_from_heuristics("Who did I talk to about hiring?")
    assert plan.intent == QueryIntent.SEMANTIC_SEARCH
    assert plan.semantic_query is not None


def test_heuristic_proper_noun_name_tokens() -> None:
    plan = plan_from_heuristics("Cynthia Johanson")
    assert plan.name_tokens == ["cynthia", "johanson"]
