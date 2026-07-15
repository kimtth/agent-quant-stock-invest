import asyncio

from tests.agent_framework_patterns.helpers import load_pattern


def test_retry_middleware_retries_transient_failures_with_exponential_backoff(monkeypatch) -> None:
    module = load_pattern("agent-middleware-retry.py")
    attempts = 0
    delays = []

    async def next_handler():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "fresh data"

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    assert asyncio.run(module.retry_transient_failures(None, next_handler)) == "fresh data"
    assert attempts == 3
    assert delays == [1, 2]