# background-agents.py

## Input

Research fundamental and risk questions to ask before analysing an equity ETF.

## Output

### Expected response

```markdown
## Equity ETF Pre-Analysis Checklist

### Fundamentals
- What index or mandate does the ETF follow, and how are holdings selected and rebalanced?
- What are the number of holdings, top-ten concentration, sector and country weights, turnover, fee, assets under management, and tracking difference?
- Which issuer documents establish the fund's objective, methodology, distributions, tax treatment, and securities-lending policy?

### Risks
- How could market drawdowns, concentration, factor exposure, currency movements, derivatives, or underlying-market liquidity affect the fund?
- Are the ETF's bid-ask spread, NAV premium or discount, creation-redemption process, and closure risk appropriate for the intended use?

### Evidence to collect
Use dated prospectuses, fact sheets, holdings files, index methodology, shareholder reports, NAV history, volume and spread data, and distribution records. State evidence gaps explicitly.

This is research only and not a transaction recommendation.
```

The parent agent delegates the fundamental and risk tracks concurrently, then synthesizes their completed text results.