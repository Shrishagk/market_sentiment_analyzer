# Market Sentiment vs Trader Performance

This repository contains a reproducible Round-0 assignment analysis for Primetrade.ai: Hyperliquid trader behavior and performance joined to Bitcoin Fear/Greed sentiment at the daily level.

## Structure

- `data/`: source CSVs used by the analysis.
- `scripts/analyze_sentiment_traders.py`: reproducible analysis pipeline.
- `reports/trader_sentiment_analysis.md`: final written report with charts and tables.
- `outputs/`: generated summaries, account segments, daily metrics, model note, and charts.

## How to Run

Use the bundled Python environment available on this machine:

```powershell
C:\Users\shris\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\analyze_sentiment_traders.py
```

The script regenerates all files in `outputs/` and rewrites `reports/trader_sentiment_analysis.md`.

## Notes

The trader dataset does not include an explicit leverage column, so the report documents this limitation and uses available risk proxies: USD notional, fee burden, trade frequency, and starting-position exposure relative to trade size.
