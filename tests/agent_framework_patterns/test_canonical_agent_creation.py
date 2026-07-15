from tests.agent_framework_patterns.helpers import load_pattern


def test_valuation_snapshot_requests_verified_inputs_only() -> None:
    module = load_pattern("canonical-agent-creation.py")

    assert module.valuation_snapshot.func("msft") == (
        "MSFT: provide only independently verified price, EPS, and valuation inputs."
    )