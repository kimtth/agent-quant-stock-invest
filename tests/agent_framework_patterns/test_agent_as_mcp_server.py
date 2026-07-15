from tests.agent_framework_patterns.helpers import load_pattern


def test_realized_volatility_enforces_bounded_lookback_and_normalizes_symbol() -> None:
    module = load_pattern("agent-as-mcp-server.py")

    assert module.realized_volatility.func("msft", 20) == (
        "Request a verified 20-day realized-volatility observation for MSFT."
    )
    assert module.realized_volatility.func("MSFT", 4) == "Invalid lookback: use 5 to 252 trading days."
    assert module.realized_volatility.func("MSFT", 253) == "Invalid lookback: use 5 to 252 trading days."