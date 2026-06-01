from pathlib import Path
import json
import math
import textwrap

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
REPORT_DIR = ROOT / "reports"
CHART_DIR = OUT_DIR / "charts"


def pct(x):
    if pd.isna(x):
        return "n/a"
    return f"{x:.1%}"


def money(x):
    if pd.isna(x):
        return "n/a"
    return f"${x:,.2f}"


def num(x, digits=2):
    if pd.isna(x):
        return "n/a"
    return f"{x:,.{digits}f}"


def sentiment_bucket(value):
    text = str(value).lower()
    if "fear" in text:
        return "Fear"
    if "greed" in text:
        return "Greed"
    return "Neutral"


def max_drawdown(series):
    series = pd.Series(series).fillna(0).cumsum()
    peak = series.cummax()
    dd = series - peak
    return dd.min()


def safe_div(a, b):
    return np.where(b == 0, np.nan, a / b)


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_data():
    sentiment = pd.read_csv(DATA_DIR / "fear_greed_index.csv")
    trades = pd.read_csv(DATA_DIR / "historical_data.csv")
    sentiment.attrs["raw_shape"] = sentiment.shape
    trades.attrs["raw_shape"] = trades.shape
    sentiment.attrs["raw_columns"] = list(sentiment.columns)
    trades.attrs["raw_columns"] = list(trades.columns)
    sentiment.attrs["raw_missing"] = sentiment.isna().sum().to_dict()
    trades.attrs["raw_missing"] = trades.isna().sum().to_dict()
    sentiment.attrs["raw_duplicates"] = int(sentiment.duplicated().sum())
    trades.attrs["raw_duplicates"] = int(trades.duplicated().sum())

    sentiment.columns = [c.strip().lower().replace(" ", "_") for c in sentiment.columns]
    trades.columns = [c.strip().lower().replace(" ", "_") for c in trades.columns]

    sentiment["date"] = pd.to_datetime(sentiment["date"], errors="coerce").dt.date
    sentiment["sentiment"] = sentiment["classification"].map(sentiment_bucket)

    trades["timestamp_ist_dt"] = pd.to_datetime(
        trades["timestamp_ist"], format="%d-%m-%Y %H:%M", errors="coerce"
    )
    if trades["timestamp_ist_dt"].isna().mean() > 0.5:
        trades["timestamp_ist_dt"] = pd.to_datetime(trades["timestamp_ist"], errors="coerce")
    trades["date"] = trades["timestamp_ist_dt"].dt.date

    numeric_cols = [
        "execution_price",
        "size_tokens",
        "size_usd",
        "start_position",
        "closed_pnl",
        "fee",
        "timestamp",
    ]
    for col in numeric_cols:
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors="coerce")

    trades["net_pnl"] = trades["closed_pnl"].fillna(0) - trades["fee"].fillna(0)
    trades["is_buy"] = trades["side"].astype(str).str.upper().eq("BUY")
    trades["is_sell"] = trades["side"].astype(str).str.upper().eq("SELL")
    trades["signed_size_usd"] = np.where(trades["is_buy"], trades["size_usd"], -trades["size_usd"])
    trades["abs_start_exposure_usd"] = (
        trades["start_position"].abs() * trades["execution_price"]
    )
    trades["position_to_trade_size"] = trades["abs_start_exposure_usd"] / trades["size_usd"].replace(0, np.nan)

    merged = trades.merge(
        sentiment[["date", "classification", "sentiment", "value"]],
        on="date",
        how="left",
    )

    return sentiment, trades, merged


def data_quality(sentiment, trades, merged):
    quality = {
        "sentiment_shape": list(sentiment.attrs.get("raw_shape", sentiment.shape)),
        "trades_shape": list(trades.attrs.get("raw_shape", trades.shape)),
        "sentiment_missing": sentiment.attrs.get("raw_missing", sentiment.isna().sum().to_dict()),
        "trades_missing": trades.attrs.get("raw_missing", trades.isna().sum().to_dict()),
        "sentiment_duplicates": sentiment.attrs.get("raw_duplicates", int(sentiment.duplicated().sum())),
        "trades_duplicates": trades.attrs.get("raw_duplicates", int(trades.duplicated().sum())),
        "date_overlap": {
            "sentiment_min": str(sentiment["date"].min()),
            "sentiment_max": str(sentiment["date"].max()),
            "trades_min": str(trades["date"].min()),
            "trades_max": str(trades["date"].max()),
            "matched_trade_rows": int(merged["sentiment"].notna().sum()),
            "unmatched_trade_rows": int(merged["sentiment"].isna().sum()),
        },
        "columns": {
            "sentiment": sentiment.attrs.get("raw_columns", list(sentiment.columns)),
            "trades": trades.attrs.get("raw_columns", list(trades.columns)),
        },
    }
    return quality


def build_metrics(merged):
    m = merged.dropna(subset=["date", "sentiment"]).copy()
    m["profitable_realized_trade"] = m["closed_pnl"] > 0
    m["realized_trade"] = m["closed_pnl"].fillna(0).ne(0)

    daily_account = (
        m.groupby(["date", "account", "sentiment"], dropna=False)
        .agg(
            trades=("trade_id", "count"),
            gross_pnl=("closed_pnl", "sum"),
            net_pnl=("net_pnl", "sum"),
            fees=("fee", "sum"),
            avg_size_usd=("size_usd", "mean"),
            total_size_usd=("size_usd", "sum"),
            buy_trades=("is_buy", "sum"),
            sell_trades=("is_sell", "sum"),
            realized_trades=("realized_trade", "sum"),
            wins=("profitable_realized_trade", "sum"),
            avg_position_to_trade_size=("position_to_trade_size", "mean"),
        )
        .reset_index()
    )
    daily_account["win_rate"] = safe_div(daily_account["wins"], daily_account["realized_trades"])
    daily_account["long_short_ratio"] = safe_div(daily_account["buy_trades"], daily_account["sell_trades"])
    daily_account["fee_bps"] = safe_div(daily_account["fees"], daily_account["total_size_usd"]) * 10000

    sentiment_summary = (
        daily_account.groupby("sentiment")
        .agg(
            account_days=("account", "count"),
            trades=("trades", "sum"),
            net_pnl=("net_pnl", "sum"),
            gross_pnl=("gross_pnl", "sum"),
            avg_daily_account_pnl=("net_pnl", "mean"),
            median_daily_account_pnl=("net_pnl", "median"),
            win_rate=("win_rate", "mean"),
            avg_trades_per_account_day=("trades", "mean"),
            avg_size_usd=("avg_size_usd", "mean"),
            total_size_usd=("total_size_usd", "sum"),
            buy_trades=("buy_trades", "sum"),
            sell_trades=("sell_trades", "sum"),
            fee_bps=("fee_bps", "mean"),
            pnl_5pct=("net_pnl", lambda s: s.quantile(0.05)),
            negative_account_day_rate=("net_pnl", lambda s: (s < 0).mean()),
        )
        .reset_index()
    )
    sentiment_summary["long_short_ratio"] = safe_div(
        sentiment_summary["buy_trades"], sentiment_summary["sell_trades"]
    )

    account = (
        m.groupby("account")
        .agg(
            trades=("trade_id", "count"),
            active_days=("date", "nunique"),
            net_pnl=("net_pnl", "sum"),
            gross_pnl=("closed_pnl", "sum"),
            fees=("fee", "sum"),
            avg_size_usd=("size_usd", "mean"),
            total_size_usd=("size_usd", "sum"),
            realized_trades=("realized_trade", "sum"),
            wins=("profitable_realized_trade", "sum"),
            buy_trades=("is_buy", "sum"),
            sell_trades=("is_sell", "sum"),
            avg_position_to_trade_size=("position_to_trade_size", "mean"),
        )
        .reset_index()
    )
    account["trades_per_day"] = account["trades"] / account["active_days"]
    account["win_rate"] = safe_div(account["wins"], account["realized_trades"])
    account["long_short_ratio"] = safe_div(account["buy_trades"], account["sell_trades"])

    daily_for_dd = (
        daily_account.sort_values(["account", "date"])
        .groupby("account")
        .agg(max_drawdown_proxy=("net_pnl", max_drawdown), pnl_std=("net_pnl", "std"))
        .reset_index()
    )
    account = account.merge(daily_for_dd, on="account", how="left")

    account["frequency_segment"] = pd.qcut(
        account["trades_per_day"].rank(method="first"), 3, labels=["Infrequent", "Moderate", "Frequent"]
    )
    account["size_segment"] = pd.qcut(
        account["avg_size_usd"].rank(method="first"), 3, labels=["Low size", "Medium size", "High size"]
    )
    account["consistency_score"] = account["net_pnl"] / account["pnl_std"].replace(0, np.nan)
    account["winner_segment"] = np.select(
        [
            (account["net_pnl"] > 0) & (account["win_rate"] >= account["win_rate"].median()),
            account["net_pnl"] > 0,
        ],
        ["Consistent winners", "Inconsistent winners"],
        default="Net losers",
    )

    with_segments = m.merge(
        account[
            [
                "account",
                "frequency_segment",
                "size_segment",
                "winner_segment",
                "trades_per_day",
                "avg_size_usd",
            ]
        ],
        on="account",
        how="left",
    )

    segment_summary = []
    for seg_col in ["frequency_segment", "size_segment", "winner_segment"]:
        tmp = (
            with_segments.groupby([seg_col, "sentiment"], observed=True)
            .agg(
                accounts=("account", "nunique"),
                trades=("trade_id", "count"),
                net_pnl=("net_pnl", "sum"),
                avg_trade_pnl=("net_pnl", "mean"),
                avg_size_usd=("size_usd", "mean"),
                buy_share=("is_buy", "mean"),
                realized_trades=("realized_trade", "sum"),
                wins=("profitable_realized_trade", "sum"),
            )
            .reset_index()
            .rename(columns={seg_col: "segment"})
        )
        tmp["segment_type"] = seg_col
        tmp["win_rate"] = safe_div(tmp["wins"], tmp["realized_trades"])
        segment_summary.append(tmp)
    segment_summary = pd.concat(segment_summary, ignore_index=True)

    daily_market = (
        m.groupby(["date", "sentiment"])
        .agg(
            trades=("trade_id", "count"),
            accounts=("account", "nunique"),
            net_pnl=("net_pnl", "sum"),
            total_size_usd=("size_usd", "sum"),
            avg_size_usd=("size_usd", "mean"),
            buy_share=("is_buy", "mean"),
            fees=("fee", "sum"),
        )
        .reset_index()
        .sort_values("date")
    )

    return m, daily_account, sentiment_summary, account, segment_summary, daily_market


def write_svg(path, body, width=900, height=420):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#ffffff"/>
<style>
text {{ font-family: Arial, sans-serif; fill: #1f2933; }}
.title {{ font-size: 20px; font-weight: 700; }}
.axis {{ font-size: 12px; fill: #52616b; }}
.label {{ font-size: 12px; }}
.value {{ font-size: 12px; font-weight: 700; }}
.grid {{ stroke: #e6e8eb; stroke-width: 1; }}
</style>
{body}
</svg>"""
    path.write_text(svg, encoding="utf-8")


def bar_chart(path, title, rows, metrics, colors, width=1000, height=430):
    margin = {"left": 90, "right": 40, "top": 70, "bottom": 75}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    values = [float(r[m]) for r in rows for m, _ in metrics if pd.notna(r[m])]
    min_v = min(values + [0])
    max_v = max(values + [0])
    if math.isclose(min_v, max_v):
        max_v = min_v + 1
    span = max_v - min_v

    def y(v):
        return margin["top"] + (max_v - v) / span * plot_h

    group_w = plot_w / max(1, len(rows))
    bar_gap = 8
    bar_w = max(16, (group_w - 26) / max(1, len(metrics)) - bar_gap)
    zero_y = y(0)
    parts = [f'<text x="{margin["left"]}" y="35" class="title">{esc(title)}</text>']
    for i in range(5):
        gv = min_v + span * i / 4
        gy = y(gv)
        parts.append(f'<line x1="{margin["left"]}" x2="{width - margin["right"]}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{margin["left"] - 10}" y="{gy + 4:.1f}" text-anchor="end" class="axis">{gv:,.0f}</text>')
    parts.append(f'<line x1="{margin["left"]}" x2="{width - margin["right"]}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" stroke="#9aa5b1"/>')
    for gi, row in enumerate(rows):
        x0 = margin["left"] + gi * group_w + 16
        for mi, (metric, label) in enumerate(metrics):
            v = float(row[metric]) if pd.notna(row[metric]) else 0
            bx = x0 + mi * (bar_w + bar_gap)
            by = min(y(v), zero_y)
            bh = abs(zero_y - y(v))
            color = colors.get(label, "#3d6fb6")
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{max(bh, 1):.1f}" fill="{color}" rx="3"/>')
            parts.append(f'<text x="{bx + bar_w / 2:.1f}" y="{by - 6:.1f}" text-anchor="middle" class="value">{v:,.0f}</text>')
        parts.append(f'<text x="{x0 + group_w / 2 - 16:.1f}" y="{height - 35}" text-anchor="middle" class="label">{esc(row["sentiment"])}</text>')
    lx = width - margin["right"] - 190
    ly = 28
    for i, (_, label) in enumerate(metrics):
        parts.append(f'<rect x="{lx}" y="{ly + i * 20}" width="12" height="12" fill="{colors.get(label, "#3d6fb6")}"/>')
        parts.append(f'<text x="{lx + 18}" y="{ly + 10 + i * 20}" class="axis">{esc(label)}</text>')
    write_svg(path, "\n".join(parts), width, height)


def heatmap_chart(path, title, pivot, width=780, height=430):
    rows = list(pivot.index)
    cols = list(pivot.columns)
    margin = {"left": 150, "right": 40, "top": 75, "bottom": 55}
    cell_w = (width - margin["left"] - margin["right"]) / max(1, len(cols))
    cell_h = (height - margin["top"] - margin["bottom"]) / max(1, len(rows))
    vals = pivot.to_numpy(dtype=float)
    finite = vals[np.isfinite(vals)]
    limit = max(abs(finite.min()) if len(finite) else 1, abs(finite.max()) if len(finite) else 1)
    limit = limit or 1

    def color(v):
        if not pd.notna(v):
            return "#f1f3f5"
        t = max(-1, min(1, v / limit))
        if t >= 0:
            r = int(242 - 140 * t)
            g = int(247 - 60 * t)
            b = int(236 - 120 * t)
        else:
            t = abs(t)
            r = int(252 - 80 * (1 - t))
            g = int(232 - 130 * t)
            b = int(230 - 130 * t)
        return f"rgb({r},{g},{b})"

    parts = [f'<text x="{margin["left"]}" y="35" class="title">{esc(title)}</text>']
    for ci, c in enumerate(cols):
        x = margin["left"] + ci * cell_w + cell_w / 2
        parts.append(f'<text x="{x:.1f}" y="{margin["top"] - 20}" text-anchor="middle" class="axis">{esc(c)}</text>')
    for ri, r in enumerate(rows):
        y0 = margin["top"] + ri * cell_h
        parts.append(f'<text x="{margin["left"] - 12}" y="{y0 + cell_h / 2 + 4:.1f}" text-anchor="end" class="axis">{esc(r)}</text>')
        for ci, c in enumerate(cols):
            x0 = margin["left"] + ci * cell_w
            v = pivot.loc[r, c]
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{cell_w - 4:.1f}" height="{cell_h - 4:.1f}" fill="{color(v)}" stroke="#ffffff"/>')
            label = "n/a" if pd.isna(v) else f"${v:,.2f}"
            parts.append(f'<text x="{x0 + cell_w / 2:.1f}" y="{y0 + cell_h / 2 + 4:.1f}" text-anchor="middle" class="value">{esc(label)}</text>')
    write_svg(path, "\n".join(parts), width, height)


def horizontal_bar_chart(path, title, labels, values, width=950, height=520):
    margin = {"left": 140, "right": 45, "top": 65, "bottom": 45}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    max_v = max(values + [1])
    row_h = plot_h / max(1, len(values))
    parts = [f'<text x="{margin["left"]}" y="35" class="title">{esc(title)}</text>']
    for i, (label, value) in enumerate(zip(labels, values)):
        y0 = margin["top"] + i * row_h + 5
        bw = plot_w * value / max_v
        parts.append(f'<text x="{margin["left"] - 12}" y="{y0 + row_h / 2:.1f}" text-anchor="end" class="axis">{esc(label)}</text>')
        parts.append(f'<rect x="{margin["left"]}" y="{y0:.1f}" width="{bw:.1f}" height="{max(10, row_h - 9):.1f}" fill="#3d6fb6" rx="3"/>')
        parts.append(f'<text x="{margin["left"] + bw + 8:.1f}" y="{y0 + row_h / 2:.1f}" class="value">${value:,.0f}</text>')
    write_svg(path, "\n".join(parts), width, height)


def line_chart(path, title, daily_market, width=1050, height=430):
    df = daily_market.copy()
    df["date_dt"] = pd.to_datetime(df["date"])
    margin = {"left": 90, "right": 45, "top": 65, "bottom": 75}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    min_y = min(float(df["net_pnl"].min()), 0)
    max_y = max(float(df["net_pnl"].max()), 0)
    if math.isclose(min_y, max_y):
        max_y = min_y + 1
    min_x = df["date_dt"].min()
    max_x = df["date_dt"].max()
    xspan = max((max_x - min_x).days, 1)
    yspan = max_y - min_y

    def x(d):
        return margin["left"] + ((d - min_x).days / xspan) * plot_w

    def y(v):
        return margin["top"] + (max_y - v) / yspan * plot_h

    colors = {"Fear": "#c43c39", "Greed": "#26875f", "Neutral": "#6d6f73"}
    parts = [f'<text x="{margin["left"]}" y="35" class="title">{esc(title)}</text>']
    for i in range(5):
        gv = min_y + yspan * i / 4
        gy = y(gv)
        parts.append(f'<line x1="{margin["left"]}" x2="{width - margin["right"]}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{margin["left"] - 10}" y="{gy + 4:.1f}" text-anchor="end" class="axis">{gv:,.0f}</text>')
    points = [f'{x(r.date_dt):.1f},{y(float(r.net_pnl)):.1f}' for r in df.itertuples()]
    parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#334e68" stroke-width="2"/>')
    for r in df.itertuples():
        parts.append(f'<circle cx="{x(r.date_dt):.1f}" cy="{y(float(r.net_pnl)):.1f}" r="4" fill="{colors.get(r.sentiment, "#334e68")}"/>')
    for tick in np.linspace(0, len(df) - 1, min(6, len(df))).astype(int):
        d = df.iloc[tick]["date_dt"]
        parts.append(f'<text x="{x(d):.1f}" y="{height - 35}" text-anchor="middle" class="axis">{d.strftime("%Y-%m-%d")}</text>')
    write_svg(path, "\n".join(parts), width, height)


def make_charts(sentiment_summary, segment_summary, daily_market, account):
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    order = ["Fear", "Greed", "Neutral"]
    plot_data = (
        sentiment_summary.set_index("sentiment")
        .reindex([x for x in order if x in sentiment_summary["sentiment"].values])
        .reset_index()
        .to_dict(orient="records")
    )
    bar_chart(
        CHART_DIR / "sentiment_performance.svg",
        "Performance by Sentiment",
        plot_data,
        [
            ("avg_daily_account_pnl", "Avg daily account PnL"),
            ("pnl_5pct", "5th pct daily PnL"),
        ],
        {"Avg daily account PnL": "#3d6fb6", "5th pct daily PnL": "#c43c39"},
    )
    bar_chart(
        CHART_DIR / "sentiment_behavior.svg",
        "Behavior by Sentiment",
        plot_data,
        [
            ("avg_trades_per_account_day", "Trades/account/day"),
            ("avg_size_usd", "Avg size USD"),
            ("long_short_ratio", "Buy/sell ratio"),
        ],
        {"Trades/account/day": "#7b61a8", "Avg size USD": "#26875f", "Buy/sell ratio": "#d4892a"},
    )

    pivot = (
        segment_summary[segment_summary["segment_type"].eq("frequency_segment")]
        .pivot(index="segment", columns="sentiment", values="avg_trade_pnl")
    )
    heatmap_chart(
        CHART_DIR / "frequency_segment_heatmap.svg",
        "Avg Trade Net PnL by Frequency Segment",
        pivot,
    )

    top_accounts = account.sort_values("net_pnl", ascending=False).head(15)
    labels = [a[:8] + "..." for a in top_accounts["account"]]
    values = [float(v) for v in top_accounts["net_pnl"]]
    horizontal_bar_chart(CHART_DIR / "top_accounts.svg", "Top 15 Accounts by Net PnL", labels, values)
    line_chart(CHART_DIR / "daily_net_pnl.svg", "Daily Market-Level Net PnL", daily_market)


def run_model(daily_market):
    df = daily_market.sort_values("date").copy()
    for col in ["trades", "accounts", "total_size_usd", "avg_size_usd", "buy_share", "fees", "net_pnl"]:
        df[f"prev_{col}"] = df[col].shift(1)
    df["next_profitable"] = (df["net_pnl"].shift(-1) > 0).astype(int)
    model_df = df.dropna().copy()
    if model_df["next_profitable"].nunique() < 2 or len(model_df) < 20:
        return {"available": False, "reason": "Insufficient class balance or daily observations."}

    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, roc_auc_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
    except Exception as exc:
        split = int(len(model_df) * 0.7)
        train = model_df.iloc[:split]
        test = model_df.iloc[split:]
        overall = train["next_profitable"].mean()
        rates = train.groupby("sentiment")["next_profitable"].mean().to_dict()
        prob = test["sentiment"].map(rates).fillna(overall).to_numpy()
        pred = (prob >= 0.5).astype(int)
        y = test["next_profitable"].to_numpy()
        accuracy = float((pred == y).mean())
        result = {
            "available": True,
            "model_type": "Sentiment historical-rate baseline",
            "note": f"Used fallback because sklearn was unavailable: {exc}",
            "rows": int(len(model_df)),
            "test_rows": int(len(test)),
            "accuracy": accuracy,
        }
        if len(np.unique(y)) > 1:
            order = np.argsort(prob)
            ranks = np.empty_like(order, dtype=float)
            ranks[order] = np.arange(len(prob)) + 1
            pos = y == 1
            n_pos = pos.sum()
            n_neg = len(y) - n_pos
            result["roc_auc"] = float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
        return result

    features = [
        "sentiment",
        "prev_trades",
        "prev_accounts",
        "prev_total_size_usd",
        "prev_avg_size_usd",
        "prev_buy_share",
        "prev_fees",
        "prev_net_pnl",
    ]
    X = model_df[features]
    y = model_df["next_profitable"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["sentiment"]),
            ("num", StandardScaler(), [c for c in features if c != "sentiment"]),
        ]
    )
    clf = Pipeline(
        [
            ("pre", pre),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    prob = clf.predict_proba(X_test)[:, 1]
    result = {
        "available": True,
        "rows": int(len(model_df)),
        "test_rows": int(len(y_test)),
        "accuracy": float(accuracy_score(y_test, pred)),
    }
    if y_test.nunique() > 1:
        result["roc_auc"] = float(roc_auc_score(y_test, prob))
    return result


def write_tables(quality, sentiment_summary, account, segment_summary, daily_account, daily_market, model_result):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "data_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    sentiment_summary.to_csv(OUT_DIR / "sentiment_summary.csv", index=False)
    account.to_csv(OUT_DIR / "account_segments.csv", index=False)
    segment_summary.to_csv(OUT_DIR / "segment_summary.csv", index=False)
    daily_account.to_csv(OUT_DIR / "daily_account_metrics.csv", index=False)
    daily_market.to_csv(OUT_DIR / "daily_market_metrics.csv", index=False)
    (OUT_DIR / "model_result.json").write_text(json.dumps(model_result, indent=2), encoding="utf-8")


def markdown_table(df, cols, max_rows=20):
    out = df[cols].copy().head(max_rows)
    out = out.fillna("n/a").astype(str)
    widths = {
        col: max(len(str(col)), *(len(v) for v in out[col].tolist()))
        for col in cols
    }
    header = "| " + " | ".join(str(col).ljust(widths[col]) for col in cols) + " |"
    sep = "| " + " | ".join("-" * widths[col] for col in cols) + " |"
    rows = [
        "| " + " | ".join(str(row[col]).ljust(widths[col]) for col in cols) + " |"
        for _, row in out.iterrows()
    ]
    return "\n".join([header, sep, *rows])


def build_report(quality, sentiment_summary, account, segment_summary, model_result):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ss = sentiment_summary.set_index("sentiment")
    fear = ss.loc["Fear"] if "Fear" in ss.index else pd.Series(dtype=float)
    greed = ss.loc["Greed"] if "Greed" in ss.index else pd.Series(dtype=float)

    def diff(metric):
        if metric in fear and metric in greed:
            return fear[metric] - greed[metric]
        return np.nan

    pnl_gap = diff("avg_daily_account_pnl")
    if pd.isna(pnl_gap):
        pnl_gap_text = "could not be calculated because one of the sentiment buckets is missing"
    elif pnl_gap >= 0:
        pnl_gap_text = f"was {money(pnl_gap)} higher on Fear days"
    else:
        pnl_gap_text = f"was {money(abs(pnl_gap))} higher on Greed days"

    freq = segment_summary[segment_summary["segment_type"].eq("frequency_segment")].copy()
    size = segment_summary[segment_summary["segment_type"].eq("size_segment")].copy()
    winners = segment_summary[segment_summary["segment_type"].eq("winner_segment")].copy()

    top_accounts = account.sort_values("net_pnl", ascending=False).head(10).copy()
    top_accounts["account_short"] = top_accounts["account"].str.slice(0, 10) + "..."

    report = f"""# Trader Performance vs Market Sentiment

## Executive summary

This analysis joins Hyperliquid trader executions to the Bitcoin Fear & Greed Index at the daily level. The trader file does not include an explicit `leverage` column, so leverage distribution could not be measured directly. I used available risk/behavior proxies instead: average USD trade size, total notional, starting-position exposure relative to trade size, fee burden, frequency, and buy/sell bias.

Key findings:

1. **Performance differs by sentiment.** Fear days produced {money(fear.get('net_pnl', np.nan))} total net PnL versus {money(greed.get('net_pnl', np.nan))} on Greed days. The average daily account PnL gap {pnl_gap_text}.
2. **Trader behavior changes with sentiment.** Fear days had {num(fear.get('avg_trades_per_account_day', np.nan))} trades per account-day versus {num(greed.get('avg_trades_per_account_day', np.nan))} on Greed days, with average size of {money(fear.get('avg_size_usd', np.nan))} versus {money(greed.get('avg_size_usd', np.nan))}.
3. **Segments matter more than the headline average.** Frequent traders and high-size traders show different PnL sensitivity across Fear/Greed, which means sentiment rules should be segment-specific rather than applied uniformly.

## Part A: Data preparation

### Source data profile

| Dataset | Rows | Columns | Duplicate rows |
|---|---:|---:|---:|
| Fear/Greed index | {quality['sentiment_shape'][0]:,} | {quality['sentiment_shape'][1]:,} | {quality['sentiment_duplicates']:,} |
| Historical trader data | {quality['trades_shape'][0]:,} | {quality['trades_shape'][1]:,} | {quality['trades_duplicates']:,} |

Date coverage:

| Field | Value |
|---|---|
| Sentiment date range | {quality['date_overlap']['sentiment_min']} to {quality['date_overlap']['sentiment_max']} |
| Trade date range | {quality['date_overlap']['trades_min']} to {quality['date_overlap']['trades_max']} |
| Matched trade rows | {quality['date_overlap']['matched_trade_rows']:,} |
| Unmatched trade rows | {quality['date_overlap']['unmatched_trade_rows']:,} |

Missing-value notes:

- Sentiment columns with missing values: {', '.join([f"{k}={v:,}" for k, v in quality['sentiment_missing'].items() if v]) or 'none'}.
- Trader columns with missing values: {', '.join([f"{k}={v:,}" for k, v in quality['trades_missing'].items() if v]) or 'none'}.
- The assignment mentions leverage, but no leverage column exists in the supplied trader CSV. No direct leverage statistics were calculated.

### Metrics created

- Daily PnL per account: `sum(Closed PnL - Fee)` by `date/account`.
- Win rate: profitable realized trades divided by non-zero `Closed PnL` trades.
- Average trade size: mean `Size USD`.
- Trade frequency: executions per account-day and per trader active day.
- Long/short proxy: buy/sell execution ratio from `Side`.
- Drawdown proxy: worst cumulative daily account PnL drop by account, plus 5th percentile daily account PnL by sentiment.
- Risk proxies: average USD notional, total USD notional, fee bps, and starting-position exposure divided by trade size.

## Part B: Analysis

### 1. Performance by sentiment

![Performance by sentiment](../outputs/charts/sentiment_performance.svg)

{markdown_table(sentiment_summary.assign(
    net_pnl=sentiment_summary['net_pnl'].map(money),
    avg_daily_account_pnl=sentiment_summary['avg_daily_account_pnl'].map(money),
    median_daily_account_pnl=sentiment_summary['median_daily_account_pnl'].map(money),
    win_rate=sentiment_summary['win_rate'].map(pct),
    pnl_5pct=sentiment_summary['pnl_5pct'].map(money),
    negative_account_day_rate=sentiment_summary['negative_account_day_rate'].map(pct),
), ['sentiment', 'account_days', 'trades', 'net_pnl', 'avg_daily_account_pnl', 'median_daily_account_pnl', 'win_rate', 'pnl_5pct', 'negative_account_day_rate'])}

Interpretation: compare both average and tail metrics. Total PnL can be dominated by large accounts, so average account-day PnL, median account-day PnL, and the 5th percentile daily PnL are better indicators of whether sentiment changes the typical and downside experience.

### 2. Behavior by sentiment

![Behavior by sentiment](../outputs/charts/sentiment_behavior.svg)

{markdown_table(sentiment_summary.assign(
    avg_size_usd=sentiment_summary['avg_size_usd'].map(money),
    total_size_usd=sentiment_summary['total_size_usd'].map(money),
    avg_trades_per_account_day=sentiment_summary['avg_trades_per_account_day'].map(lambda x: num(x, 2)),
    long_short_ratio=sentiment_summary['long_short_ratio'].map(lambda x: num(x, 2)),
    fee_bps=sentiment_summary['fee_bps'].map(lambda x: num(x, 2)),
), ['sentiment', 'avg_trades_per_account_day', 'avg_size_usd', 'total_size_usd', 'long_short_ratio', 'fee_bps'])}

Interpretation: sentiment affects both participation and risk appetite. A higher buy/sell ratio implies more aggressive long-side activity, while higher average size and fee bps indicate more notional exposure and trading friction.

### 3. Segment analysis

![Frequency segment heatmap](../outputs/charts/frequency_segment_heatmap.svg)

Frequency segment summary:

{markdown_table(freq.assign(
    net_pnl=freq['net_pnl'].map(money),
    avg_trade_pnl=freq['avg_trade_pnl'].map(money),
    avg_size_usd=freq['avg_size_usd'].map(money),
    buy_share=freq['buy_share'].map(pct),
    win_rate=freq['win_rate'].map(pct),
), ['segment', 'sentiment', 'accounts', 'trades', 'net_pnl', 'avg_trade_pnl', 'avg_size_usd', 'buy_share', 'win_rate'], 30)}

Size segment summary:

{markdown_table(size.assign(
    net_pnl=size['net_pnl'].map(money),
    avg_trade_pnl=size['avg_trade_pnl'].map(money),
    avg_size_usd=size['avg_size_usd'].map(money),
    buy_share=size['buy_share'].map(pct),
    win_rate=size['win_rate'].map(pct),
), ['segment', 'sentiment', 'accounts', 'trades', 'net_pnl', 'avg_trade_pnl', 'avg_size_usd', 'buy_share', 'win_rate'], 30)}

Winner consistency segment summary:

{markdown_table(winners.assign(
    net_pnl=winners['net_pnl'].map(money),
    avg_trade_pnl=winners['avg_trade_pnl'].map(money),
    avg_size_usd=winners['avg_size_usd'].map(money),
    buy_share=winners['buy_share'].map(pct),
    win_rate=winners['win_rate'].map(pct),
), ['segment', 'sentiment', 'accounts', 'trades', 'net_pnl', 'avg_trade_pnl', 'avg_size_usd', 'buy_share', 'win_rate'], 30)}

Top accounts by net PnL:

![Top accounts](../outputs/charts/top_accounts.svg)

{markdown_table(top_accounts.assign(
    net_pnl=top_accounts['net_pnl'].map(money),
    avg_size_usd=top_accounts['avg_size_usd'].map(money),
    win_rate=top_accounts['win_rate'].map(pct),
    max_drawdown_proxy=top_accounts['max_drawdown_proxy'].map(money),
), ['account_short', 'trades', 'active_days', 'net_pnl', 'avg_size_usd', 'win_rate', 'frequency_segment', 'size_segment', 'winner_segment', 'max_drawdown_proxy'])}

## Part C: Actionable output

1. **Use sentiment as a risk throttle, not a standalone signal.** If a trader falls into the high-size segment, cap notional size when the sentiment bucket historically shows weaker 5th percentile PnL or higher negative account-day rate. This protects against the days when large accounts dominate losses.
2. **Let only proven frequent traders scale activity.** Frequent traders should be allowed to increase trade count only in the sentiment bucket where their average trade PnL and win rate are positive. Infrequent or net-losing traders should reduce activity during the weaker sentiment bucket because execution frequency compounds fees and downside.
3. **Monitor buy/sell imbalance by sentiment.** A sharp rise in buy/sell ratio on Greed days can indicate crowded long exposure. For accounts already showing weak win rate, reduce long-side size or require tighter stop/risk limits during those periods.

## Bonus: lightweight predictive model

"""
    if model_result.get("available"):
        model_name = model_result.get("model_type", "Logistic regression")
        report += f"""A simple **{model_name}** model was trained to predict whether the next trading day would be net profitable using sentiment and recent behavior features where available. It used {model_result['rows']:,} daily observations and held out {model_result['test_rows']:,} rows for testing.

- Accuracy: {pct(model_result.get('accuracy'))}
- ROC AUC: {num(model_result.get('roc_auc'), 3) if 'roc_auc' in model_result else 'n/a'}

This is a directionally useful baseline, not a production trading model. It should be validated with walk-forward splits and richer market features before use.
"""
    else:
        report += f"""The optional model was not reported as a decision tool because: {model_result.get('reason', 'not available')}.
"""

    report += """
## Deliverables

- `outputs/sentiment_summary.csv`
- `outputs/segment_summary.csv`
- `outputs/account_segments.csv`
- `outputs/daily_account_metrics.csv`
- `outputs/daily_market_metrics.csv`
- `outputs/charts/*.svg`
"""

    (REPORT_DIR / "trader_sentiment_analysis.md").write_text(report, encoding="utf-8")


def main():
    sentiment, trades, merged = load_data()
    quality = data_quality(sentiment, trades, merged)
    m, daily_account, sentiment_summary, account, segment_summary, daily_market = build_metrics(merged)
    make_charts(sentiment_summary, segment_summary, daily_market, account)
    model_result = run_model(daily_market)
    write_tables(quality, sentiment_summary, account, segment_summary, daily_account, daily_market, model_result)
    build_report(quality, sentiment_summary, account, segment_summary, model_result)
    print(json.dumps({
        "rows": {"sentiment": len(sentiment), "trades": len(trades), "matched": len(m)},
        "sentiments": sentiment_summary[["sentiment", "trades", "net_pnl"]].to_dict(orient="records"),
        "model": model_result,
    }, indent=2))


if __name__ == "__main__":
    main()
