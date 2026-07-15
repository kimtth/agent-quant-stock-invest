import inspect

from tests.agent_framework_patterns.helpers import load_pattern


def test_risk_and_limitations_evaluator_rejects_trade_advice() -> None:
    module = load_pattern("agent-evaluation-local.py")
    predicate = inspect.getclosurevars(module.includes_risk_and_limitations).nonlocals["func"]

    assert predicate("Risk and limitation disclosures are included.")
    assert not predicate("Risk discussion without the required disclosure.")
    assert not predicate("Risk and limitation noted; buy now.")