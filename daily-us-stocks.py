"""Daily US-stock monitor: fetch recent daily bars for the 5 US stocks
from the user's Gate screenshot (NVDA, AMD, MU, AVGO, TSLA) via the
public Yahoo Finance chart API (no key), plus SPCX (SpaceX token on
Gate) via Gate's public spot ticker API (no key). Writes a daily report
to signals/us-stocks.md.

Signals are TREND-START entry alerts, not after-the-fact big-move
alerts: (1) close breaks above the previous 20 trading days' highest
close (breakout), (2) MACD 19/39/9 DIF crosses above DEA today (MACD
turns up). No signal can predict a rise before it happens - these fire
when a trend is just starting, and a breakout can still pull back.
PRICE MONITORING ONLY - no orders, no API keys, no real money.
"""
import json
import os
from datetime import datetime, timezone

import requests

STOCKS = [
    ("NVDA", "英伟达"),
    ("AMD", "超威半导体"),
    ("MU", "美光科技"),
    ("AVGO", "博通公司"),
    ("TSLA", "特斯拉"),
]
GATE_API = "https://api.gateio.ws/api/v4/spot/tickers"


def ema(values, span):
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def fetch_yahoo(symbol):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, params={"range": "3mo", "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
    return closes


def stock_signals(closes):
    """Return (last, prev, pct, [signal strings]) for one stock."""
    last, prev = closes[-1], closes[-2]
    pct = (last / prev - 1) * 100
    signals = []
    if len(closes) > 20 and last > max(closes[-21:-1]):
        signals.append("突破20日高点")
    if len(closes) > 50:
        dif = [a - b for a, b in zip(ema(closes, 19), ema(closes, 39))]
        dea = ema(dif, 9)
        if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
            signals.append("MACD刚翻多")
    return last, prev, pct, signals


def fetch_spcx():
    r = requests.get(GATE_API, params={"currency_pair": "SPCX_USDT"},
                     timeout=30)
    r.raise_for_status()
    t = r.json()[0]
    last = float(t["last"])
    change = float(t["change_percentage"])
    prev = last / (1 + change / 100)
    return last, prev


def main():
    rows = []
    for symbol, name in STOCKS:
        try:
            closes = fetch_yahoo(symbol)
            last, prev, pct, signals = stock_signals(closes)
            rows.append((symbol, name, last, prev, pct, signals, None))
        except Exception as e:
            rows.append((symbol, name, None, None, None, [], str(e)))
    try:
        last, prev = fetch_spcx()
        pct = (last / prev - 1) * 100
        rows.append(("SPCX", "SpaceX（Gate 代币）", last, prev, pct, [], None))
    except Exception as e:
        rows.append(("SPCX", "SpaceX（Gate 代币）", None, None, None, [], str(e)))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# 美股每日监控（只看价格，不下单）", "", f"- 更新时间：{now}",
             "- 数据：Yahoo Finance（NVDA/AMD/MU/AVGO/TSLA）+ Gate 公开接口（SPCX）",
             "- 信号说明：收盘突破 20 日最高价，或 MACD 19/39/9 刚翻多，都算趋势刚启动，不保证涨，突破也可能回落",
             "", "| 代码 | 名称 | 最新价 | 日涨跌 | 信号 |",
             "| --- | --- | --- | --- | --- |"]
    alerts = []
    for symbol, name, last, prev, pct, signals, err in rows:
        if err is not None or last is None:
            lines.append(f"| {symbol} | {name} | 获取失败 | - | - |")
            continue
        sig = "、".join(signals) if signals else ""
        if signals:
            alerts.append(f"{symbol}（{sig}）")
        lines.append(f"| {symbol} | {name} | ${last:,.2f} | {pct:+.2f}% | {sig} |")
    lines.append("")
    if alerts:
        lines.append("## 提醒\n\n- 今日趋势刚启动：" + "，".join(alerts))
    else:
        lines.append("## 提醒\n\n- 今日无趋势启动信号。")
    lines.append("")
    lines.append("说明：价格是上一交易日收盘价附近的最新价，仅供参考，不是投资建议。SPCX 是 SpaceX 在 Gate 上的代币，不是上市公司股票，没有趋势信号。")
    report = "\n".join(lines) + "\n"

    out_dir = os.environ.get("SIGNAL_OUT", "signals")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "us-stocks.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    state_path = os.path.join(out_dir, "us-stocks-alerts.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "alerts": alerts}, f, ensure_ascii=False, indent=2)
    print(report)
    print("wrote", path, "and", state_path)


if __name__ == "__main__":
    main()
