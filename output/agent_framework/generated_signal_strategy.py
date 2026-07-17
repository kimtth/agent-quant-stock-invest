import pandas as pd
import numpy as np
import ta

# Hypothesis: MSFT is held only in a confirmed long-term uptrend with positive
# intermediate momentum: SMA(50) > SMA(200) and RSI(14) > 50.
df = pd.read_csv(INPUT_PATH)
close_col = 'Close'
for c in df.columns:
    if c.lower() == 'close':
        close_col = c
    elif c.lower() in ('adj close', 'adj_close', 'adjusted close') and close_col not in df.columns:
        close_col = c
close = pd.to_numeric(df[close_col], errors='coerce')

sma_fast = close.rolling(window=50, min_periods=50).mean()
sma_slow = close.rolling(window=200, min_periods=200).mean()
rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi()
regime = ((sma_fast > sma_slow) & (rsi > 50)).fillna(False)
prior_regime = regime.shift(1).fillna(False)
buy = regime & (~prior_regime)
sell = (~regime) & prior_regime

out = pd.DataFrame({'BuySignal': buy.astype(int), 'SellSignal': sell.astype(int)})
out['Description'] = np.where(buy, 'Buy: SMA50 > SMA200 and RSI(14) > 50', np.where(sell, 'Sell: SMA50 <= SMA200 or RSI(14) <= 50', 'Hold'))
out = out[['BuySignal', 'SellSignal', 'Description']]
out.to_csv(OUTPUT_PATH, index=False)

# Backtest convention: each close-based signal is traded at the next session's close.
asset_return = close.pct_change().fillna(0.0)
position = regime.shift(1).fillna(False).astype(float)
strategy_return = position * asset_return
initial_value = 10000.0
equity = initial_value * (1.0 + strategy_return).cumprod()
final_value = float(equity.iloc[-1])
total_return = final_value / initial_value - 1.0
n_days = len(df) - 1
cagr = (final_value / initial_value) ** (252.0 / n_days) - 1.0
max_drawdown = float((equity / equity.cummax() - 1.0).min())
volatility = float(strategy_return.std(ddof=1))
sharpe = float(np.sqrt(252.0) * strategy_return.mean() / volatility) if volatility > 0 else np.nan
print({'rows': len(out), 'final_value': final_value, 'total_return': total_return, 'CAGR': cagr, 'max_drawdown': max_drawdown, 'Sharpe_ratio': sharpe})