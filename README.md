# Trader Performance vs Market Sentiment

This project analyzes how Bitcoin market sentiment, measured by the Fear & Greed Index, relates to Hyperliquid trader behavior and performance. It was prepared for the Primetrade.ai Data Science/Analytics Intern Round-0 assignment.

The analysis joins trader executions to sentiment labels at the daily level, builds account/day metrics, compares Fear vs Greed regimes, segments traders by behavior, and proposes strategy recommendations.

## Deliverables

- `reports/submission_summary.md` - short evaluator-facing write-up with methodology, insights, and recommendations.
- `reports/trader_sentiment_analysis.md` - detailed analysis report with charts and tables.
- `scripts/analyze_sentiment_traders.py` - reproducible analysis script.
- `outputs/` - generated CSV summaries, model result, and SVG charts.
- `data/` - input CSV files used by the script.

## Repository Structure

```text
.
+-- data/
|   +-- fear_greed_index.csv
|   +-- historical_data.csv
+-- outputs/
|   +-- charts/
|   +-- account_segments.csv
|   +-- daily_account_metrics.csv
|   +-- daily_market_metrics.csv
|   +-- segment_summary.csv
|   +-- sentiment_summary.csv
+-- reports/
|   +-- submission_summary.md
|   +-- trader_sentiment_analysis.md
+-- scripts/
|   +-- analyze_sentiment_traders.py
+-- README.md
+-- requirements.txt
```

## Setup

Python 3.10+ is recommended.

Install the required packages:

```bash
pip install -r requirements.txt
```

Minimum required packages are `pandas` and `numpy`. `scikit-learn` is used only for the optional predictive model.

If installing only the minimum dependencies:

```bash
pip install pandas numpy
```

If `scikit-learn` is unavailable, the script automatically falls back to a dependency-light sentiment baseline for the optional predictive-model section.

## How to Run

From the project root:

```bash
python scripts/analyze_sentiment_traders.py
```

The script regenerates:

- `outputs/*.csv`
- `outputs/charts/*.svg`
- `outputs/data_quality.json`
- `outputs/model_result.json`
- `reports/trader_sentiment_analysis.md`

## Methodology Summary

1. Load the Fear & Greed dataset and historical trader dataset.
2. Parse trader timestamps and align both datasets by calendar date.
3. Create daily and account-level metrics:
   - net PnL as `Closed PnL - Fee`
   - win rate
   - trade frequency
   - average trade size
   - buy/sell ratio
   - fee burden
   - drawdown proxy
4. Compare performance and behavior across Fear, Greed, and Neutral days.
5. Segment traders into frequency, size, and consistency groups.
6. Generate strategy recommendations from the observed segment-level patterns.

## Important Data Note

The assignment mentions leverage, but the supplied trader CSV does not include an explicit leverage column. The analysis documents this limitation and uses available risk proxies instead: USD notional, fee burden, trade frequency, and starting-position exposure relative to trade size.
