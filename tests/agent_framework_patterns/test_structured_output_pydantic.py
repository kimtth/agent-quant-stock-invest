import pytest
from pydantic import ValidationError

from tests.agent_framework_patterns.helpers import load_pattern


def test_investment_thesis_validates_confidence_and_round_trips_json() -> None:
    module = load_pattern("structured-output-pydantic.py")
    thesis = module.InvestmentThesis(
        ticker="MSFT",
        thesis="Evidence-led research.",
        catalysts=["Demand"],
        risks=["Valuation"],
        limitations=["Historical data"],
        confidence=0.6,
    )

    assert module.InvestmentThesis.model_validate_json(thesis.model_dump_json()) == thesis
    with pytest.raises(ValidationError):
        module.InvestmentThesis(**{**thesis.model_dump(), "confidence": 1.01})