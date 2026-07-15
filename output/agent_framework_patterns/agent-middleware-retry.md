# agent-middleware-retry.py

## Input

Draft a dated research checklist for analysing an ETF.

## Output

### Expected response

```markdown
## ETF Research Checklist — 2026-07-15

1. **Identity and mandate** — Verify the legal name, ticker, issuer, benchmark, prospectus date, and replication method.
2. **Portfolio composition** — Record holdings, top-ten concentration, sector and country exposure, turnover, fee, assets under management, and tracking difference.
3. **Costs and trading** — Compare the expense ratio, tracking difference, assets under management, trading volume, NAV premium or discount, and bid-ask spread.
4. **Risk review** — Assess market, concentration, liquidity, currency, derivatives, counterparty, and tax risks that apply to the fund.
5. **Peer comparison** — Compare at least three similar funds on exposure, cost, liquidity, performance, and implementation characteristics using the same as-of date.
6. **Limitations** — Re-check price, NAV, spreads, holdings, flows, and issuer announcements on the intended review date; historical returns do not predict future outcomes.

This is a research checklist, not a trade recommendation.
```

Transient transport failures are retried up to three times with exponential backoff before the middleware re-raises the error.