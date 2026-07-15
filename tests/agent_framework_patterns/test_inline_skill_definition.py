from tests.agent_framework_patterns.helpers import load_pattern


def test_risk_skill_exposes_read_only_research_guardrails() -> None:
    module = load_pattern("inline-skill-definition.py")

    guardrails = module.investment_guardrails()
    assert "Verify sources" in guardrails
    assert "never execute or recommend a trade" in guardrails