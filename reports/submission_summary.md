# Trader Performance vs Market Sentiment: Short Summary

## Methodology

I joined the Hyperliquid trader dataset with the Bitcoin Fear/Greed Index at the daily level. Trader timestamps were parsed from `Timestamp IST`, converted to dates, and merged to sentiment dates. The analysis uses `Closed PnL - Fee` as net PnL and builds daily/account metrics: trade count, win rate, average USD size, buy/sell ratio, fee burden, and drawdown proxy. The supplied trader file does not include a leverage column, so leverage was documented as unavailable and replaced with risk proxies such as USD notional and starting-position exposure relative to trade size.

## Key Insights

1. Fear days generated lower total net PnL than Greed days, but higher average daily account PnL: Fear produced about `$3.98M` net PnL versus `$4.78M` on Greed days, while average daily account PnL was `$5,037.87` on Fear versus `$4,067.44` on Greed.
2. Risk and activity increased on Fear days. Fear days had `105.36` trades per account-day versus `76.91` on Greed days, and average trade size was `$8,529.86` versus `$5,954.63`.
3. Segment behavior matters. Frequent traders stayed profitable across both Fear and Greed, while net-losing traders performed especially poorly during Greed days, suggesting that sentiment rules should differ by trader archetype.

## Strategy Recommendations

1. Use sentiment as a risk throttle. During sentiment regimes with worse downside metrics, especially for high-size traders, reduce notional size and enforce tighter loss limits.
2. Allow trade-frequency scaling only for proven frequent or consistent-winning traders. Infrequent and net-losing traders should avoid increasing activity during weaker sentiment buckets because fees and poor timing compound losses.
3. Monitor buy/sell imbalance during Greed. If long-side activity becomes crowded and the trader has weak historical win rate, reduce long exposure or require stricter confirmation before entering.

## Deliverables

- Reproducible script: `scripts/analyze_sentiment_traders.py`
- Setup/run instructions: `README.md`
- Full report: `reports/trader_sentiment_analysis.md`
- Short summary: `reports/submission_summary.md`
- Output charts/tables: `outputs/`
