## Role:
- You are a quant trading professional.

## Task:  
- Use the ta library (URL: [https://github.com/bukosabino/ta](https://github.com/bukosabino/ta)) to generate questions by combining indicators from the **Supported Indicators** list below. 
- The goal is to find the best returns for MSFT stock by testing different indicator combinations. 
- Generate at least 50 indicator combinations for strategies involving fewer than 5 indicators. 
- The output should be aligned with **Desiresd output**.

## Supported Indicators:

### Volume

 - Accumulation/Distribution Index (ADI)
 - On-Balance Volume (OBV)
 - On-Balance Volume mean (OBV mean)
 - Chaikin Money Flow (CMF)
 - Force Index (FI)
 - Ease of Movement (EoM, EMV)
 - Volume-price Trend (VPT)
 - Negative Volume Index (NVI)

### Volatility

 - Average True Range (ATR)
 - Bollinger Bands (BB)
 - Keltner Channel (KC)
 - Donchian Channel (DC)

### Trend
 - Moving Average Convergence Divergence (MACD)
 - Average Directional Movement Index (ADX)
 - Vortex Indicator (VI)
 - Trix (TRIX)
 - Mass Index (MI)
 - Commodity Channel Index (CCI)
 - Detrended Price Oscillator (DPO)
 - KST Oscillator (KST)
 - Ichimoku Kinkō Hyō (Ichimoku)

### Momentum
 - Money Flow Index (MFI)
 - Relative Strength Index (RSI)
 - True strength index (TSI)
 - Ultimate Oscillator (UO)
 - Stochastic Oscillator (SR)
 - Williams %R (WR)
 - Awesome Oscillator (AO)

### Others
 - Daily Return (DR)
 - Cumulative Return (CR)


## Desired output:

### Example 1:  
 Run a complete stock analysis for MSFT from 1995-01-01 to today.  
 Generate buy/sell signals using a 10-day Moving Average.  
 Backtest the strategy and provide performance metrics.

### Example 2:  
 Run a complete stock analysis for MSFT from 1995-01-01 to today.  
 Generate buy/sell signals using a 20-day Moving Average and MACD.  
 sBacktest the strategy and provide performance metrics.