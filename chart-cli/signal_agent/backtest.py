"""Streaming backtest of the agent-generated buy and sell signals."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .features import TRADING_PERIODS
from .models import (
    BacktestFrame,
    BacktestMetrics,
    BacktestRequest,
    BacktestSummary,
    StrategyPlan,
    Trade,
)

CHART_POINTS = 120
RECENT_TRADES = 12
MIN_BARS = 30

DEFAULT_PLAN = StrategyPlan(
    name="No generated signal",
    rationale="The signal generator did not produce a validated strategy.",
)


def _downsample(values: list[float], limit: int = CHART_POINTS) -> list[float]:
    if len(values) <= limit:
        return [round(value, 4) for value in values]
    step = len(values) / limit
    sampled = [values[min(len(values) - 1, int(i * step))] for i in range(limit)]
    sampled[-1] = values[-1]
    return [round(value, 4) for value in sampled]


def _stamp(timestamps: list[float], index: int) -> str:
    if index < len(timestamps):
        try:
            return datetime.fromtimestamp(
                timestamps[index] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            pass
    return f"bar {index + 1}"


class BacktestEngine:
    """Backtest the validated buy and sell signals emitted by an agent-authored script."""

    def __init__(
        self,
        request: BacktestRequest,
        plan: StrategyPlan,
        buy_signals: list[bool] | None = None,
        sell_signals: list[bool] | None = None,
    ) -> None:
        self.request = request
        self.closes = [
            float(value)
            for value in request.history
            if np.isfinite(value) and value > 0
        ]
        self.plan = plan
        self.buy_signals = list(buy_signals or [])
        self.sell_signals = list(sell_signals or [])
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = []
        self.metrics = BacktestMetrics(
            initial_capital=request.initial_capital,
            final_value=request.initial_capital,
            total_return_pct=0.0,
            cagr_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe=0.0,
            win_rate_pct=0.0,
            exposure_pct=0.0,
            trade_count=0,
        )

    @property
    def usable(self) -> bool:
        return len(self.closes) >= MIN_BARS

    def frames(self) -> Iterator[BacktestFrame]:
        """Yield at most `max_frames` progress frames across the whole series."""
        closes = pd.Series(self.closes, dtype="float64")
        total = len(closes)
        returns = closes.pct_change().fillna(0.0).to_numpy()
        prices = closes.to_numpy()

        capital = self.request.initial_capital
        equity = capital
        peak = capital
        position = 0
        bars_in_market = 0
        entry_equity = capital
        max_drawdown = 0.0
        strategy_returns: list[float] = []
        every = max(1, total // max(1, self.request.max_frames))

        for index in range(total):
            bar_return = position * float(returns[index])
            strategy_returns.append(bar_return)
            equity *= 1 + bar_return
            if position:
                bars_in_market += 1
            peak = max(peak, equity)
            drawdown = equity / peak - 1 if peak else 0.0
            max_drawdown = min(max_drawdown, drawdown)
            self.equity_curve.append(equity)

            buy = index < len(self.buy_signals) and self.buy_signals[index]
            sell = index < len(self.sell_signals) and self.sell_signals[index]
            if position == 0 and buy:
                position = 1
                entry_equity = equity
                self.trades.append(
                    Trade(
                        side="BUY",
                        index=index,
                        time=_stamp(self.request.timestamps, index),
                        price=float(prices[index]),
                        equity=equity,
                    )
                )
            elif position == 1 and sell:
                position = 0
                self.trades.append(
                    Trade(
                        side="SELL",
                        index=index,
                        time=_stamp(self.request.timestamps, index),
                        price=float(prices[index]),
                        equity=equity,
                        profit_pct=(equity / entry_equity - 1) * 100 if entry_equity else 0.0,
                    )
                    )

            self._update_metrics(
                equity=equity,
                bars=index + 1,
                bars_in_market=bars_in_market,
                max_drawdown=max_drawdown,
                strategy_returns=strategy_returns,
            )

            if index % every == 0 or index == total - 1:
                yield BacktestFrame(
                    symbol=self.request.symbol,
                    index=index + 1,
                    total=total,
                    time=_stamp(self.request.timestamps, index),
                    price=float(prices[index]),
                    position=position,
                    equity=equity,
                    drawdown_pct=drawdown * 100,
                    equity_curve=_downsample(self.equity_curve),
                    metrics=self.metrics,
                    trades=self.trades[-RECENT_TRADES:],
                )

    def _update_metrics(
        self,
        *,
        equity: float,
        bars: int,
        bars_in_market: int,
        max_drawdown: float,
        strategy_returns: list[float],
    ) -> None:
        capital = self.request.initial_capital
        years = max(bars / TRADING_PERIODS, 1 / TRADING_PERIODS)
        deviation = float(np.std(strategy_returns)) if len(strategy_returns) > 1 else 0.0
        closed = [trade for trade in self.trades if trade.side == "SELL"]
        wins = sum(1 for trade in closed if trade.profit_pct > 0)
        self.metrics = BacktestMetrics(
            initial_capital=capital,
            final_value=equity,
            total_return_pct=(equity / capital - 1) * 100 if capital else 0.0,
            cagr_pct=((equity / capital) ** (1 / years) - 1) * 100 if capital else 0.0,
            max_drawdown_pct=max_drawdown * 100,
            sharpe=0.0
            if deviation == 0
            else float(np.mean(strategy_returns) / deviation * np.sqrt(TRADING_PERIODS)),
            win_rate_pct=(wins / len(closed) * 100) if closed else 0.0,
            exposure_pct=(bars_in_market / bars * 100) if bars else 0.0,
            trade_count=len(closed),
        )

    def summary(self, *, mode: str, verdict: str, error: str = "") -> BacktestSummary:
        return BacktestSummary(
            symbol=self.request.symbol,
            mode="agent" if mode == "agent" else "offline",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            criteria=self.request.criteria,
            plan=self.plan,
            metrics=self.metrics,
            equity_curve=_downsample(self.equity_curve),
            trades=self.trades[-RECENT_TRADES:],
            verdict=verdict,
            error=error,
        )


def rule_based_verdict(engine: BacktestEngine) -> str:
    """Plain-language read of the metrics when no agent is available."""
    metrics = engine.metrics
    if metrics.trade_count == 0:
        return (
            "The strategy never completed a round trip on this series, so the result "
            "reflects cash rather than the signal."
        )
    quality = (
        "held up"
        if metrics.total_return_pct > 0 and metrics.max_drawdown_pct > -25
        else "struggled"
    )
    return (
        f"The generated strategy {quality}: {metrics.total_return_pct:+.1f}% total return over {metrics.trade_count} closed "
        f"trades, {metrics.win_rate_pct:.0f}% of them profitable, with a "
        f"{metrics.max_drawdown_pct:.1f}% worst drawdown and {metrics.exposure_pct:.0f}% "
        "time in market. Costs, slippage, and taxes are excluded."
    )
