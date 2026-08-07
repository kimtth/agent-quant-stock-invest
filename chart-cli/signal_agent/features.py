"""Deterministic technical features and the rule-based fallback strategy."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .models import (
    AssetFeatures,
    AssetQuote,
    AssetSignal,
    MarketSnapshot,
    RiskAdjustment,
    RiskLevel,
    RiskReview,
    TechnicalRead,
)

FAST_WINDOW = 10
SLOW_WINDOW = 30
RSI_WINDOW = 14
TRADING_PERIODS = 252


def _rsi(closes: pd.Series, window: int = RSI_WINDOW) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return float(100 - 100 / (1 + rs))


def extract_features(quote: AssetQuote) -> AssetFeatures | None:
    """Compute moving averages, RSI, momentum, volatility, and drawdown."""
    closes = pd.Series(
        [value for value in quote.history if np.isfinite(value) and value > 0],
        dtype="float64",
    )
    if len(closes) < 5:
        return None

    fast = float(closes.rolling(min(FAST_WINDOW, len(closes))).mean().iloc[-1])
    slow = float(closes.rolling(min(SLOW_WINDOW, len(closes))).mean().iloc[-1])
    returns = closes.pct_change().dropna()
    volatility = (
        float(returns.std(ddof=0) * np.sqrt(TRADING_PERIODS) * 100)
        if len(returns) > 1
        else 0.0
    )
    momentum = float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)
    drawdown = float((closes.iloc[-1] / closes.cummax().iloc[-1] - 1) * 100)
    spread = (fast - slow) / slow * 100 if slow else 0.0
    trend = "up" if spread > 0.25 else "down" if spread < -0.25 else "flat"

    return AssetFeatures(
        symbol=quote.symbol,
        kind=quote.kind,
        price=float(closes.iloc[-1]),
        change_pct=quote.change_pct,
        sma_fast=fast,
        sma_slow=slow,
        rsi=_rsi(closes),
        momentum_pct=momentum,
        volatility_pct=volatility,
        drawdown_pct=drawdown,
        trend=trend,
    )


def extract_all(snapshot: MarketSnapshot) -> list[AssetFeatures]:
    features = (extract_features(quote) for quote in snapshot.assets)
    return [item for item in features if item is not None]


def features_json(features: list[AssetFeatures]) -> str:
    """Indicator table as the JSON block every agent prompt embeds."""
    return json.dumps([item.model_dump() for item in features])


def rule_based_read(features: list[AssetFeatures]) -> TechnicalRead:
    """Transparent moving-average and RSI crossover fallback."""
    signals: list[AssetSignal] = []
    for item in features:
        overbought = item.rsi >= 70
        oversold = item.rsi <= 30
        if item.trend == "up" and not overbought:
            action, reason = "BUY", "fast SMA above slow SMA with RSI below 70"
        elif item.trend == "down" or overbought:
            action, reason = (
                "SELL",
                "fast SMA below slow SMA or RSI at overbought level",
            )
        else:
            action, reason = "HOLD", "no confirmed moving-average crossover"
        if oversold and action == "SELL":
            action, reason = (
                "HOLD",
                "downtrend but RSI oversold; waiting for confirmation",
            )

        strength = min(
            abs(item.sma_fast - item.sma_slow) / max(item.sma_slow, 1e-9), 0.05
        )
        confidence = round(min(0.35 + strength * 10, 0.85), 2)
        signals.append(
            AssetSignal(
                symbol=item.symbol,
                action=action,
                confidence=confidence,
                rationale=(
                    f"{reason}; RSI {item.rsi:.1f}, momentum {item.momentum_pct:+.1f}%."
                ),
            )
        )

    breadth = sum(1 for signal in signals if signal.action == "BUY")
    total = max(len(signals), 1)
    return TechnicalRead(
        market_note=(
            f"Rule-based scan of {total} assets: {breadth} in confirmed uptrend, "
            f"{total - breadth} neutral or weakening."
        ),
        signals=signals,
    )


def rule_based_risk(features: list[AssetFeatures], read: TechnicalRead) -> RiskReview:
    """Cap exposure by realised volatility and current drawdown."""
    by_symbol = {item.symbol: item for item in features}
    adjustments: list[RiskAdjustment] = []
    for signal in read.signals:
        item = by_symbol.get(signal.symbol)
        volatility = item.volatility_pct if item else 40.0
        drawdown = item.drawdown_pct if item else 0.0
        cap = 15.0 if volatility < 25 else 10.0 if volatility < 60 else 5.0
        if drawdown < -20:
            cap = min(cap, 5.0)
        action = signal.action
        confidence = signal.confidence
        if action == "BUY" and volatility > 90:
            action, confidence = "HOLD", min(confidence, 0.4)
        adjustments.append(
            RiskAdjustment(
                symbol=signal.symbol,
                action=action,
                confidence=round(confidence, 2),
                max_position_pct=cap,
                risk_note=(
                    f"annualised volatility {volatility:.0f}%, "
                    f"drawdown {drawdown:.1f}% from period high."
                ),
            )
        )

    average_volatility = (
        sum(item.volatility_pct for item in features) / len(features)
        if features
        else 0.0
    )
    level: RiskLevel = (
        "LOW"
        if average_volatility < 25
        else "MEDIUM"
        if average_volatility < 55
        else "HIGH"
    )
    return RiskReview(
        portfolio_risk=level,
        risk_summary=(
            f"Average annualised volatility {average_volatility:.0f}%. "
            "Position caps scale down as volatility and drawdown rise."
        ),
        adjustments=adjustments,
    )
