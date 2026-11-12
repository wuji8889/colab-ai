"""Crypto monitor (30-min polling, 24/7): fetch daily bars for 8 major
coins (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, USDT pairs) via the
public Binance US API (no key). Writes a report to signals/crypto.md
and current alerts to signals/crypto-alerts.json.

Signals are TREND-START entry alerts: (1) last price breaks above the
previous 20 trading days' highest close (breakout), (2) on the daily
summary run only (00:00-00:59 UTC), MACD 19/39/9 DIF crosses above DEA
(MACD turns up). During the day a 24h move of 5% or more vs the previous
daily close is also flagged. No signal can predict a rise before it
happens - these fire when a trend is just starting, and a breakout can
still pull back. PRICE MONITORING ONLY - no orders, no API keys, no
real money. (Separate from the daily BTC paper-trading signal job.)
"""
import json
import os
from datetime import datetime, timezone

import requests

COINS = [
    ("BTCUSDT", "BTC", "比特币"),
    ("ETHUSDT", "ETH", "以太坊"),
    ("SOLUSDT", "SOL", "Solana"),
    ("BNBUSDT", "BNB", "币安币"),
    ("XRPUSDT", "XRP", "瑞波币"),
    ("DOGEUSDT", "DOGE", "狗狗币"),
    ("ADAUSDT", "ADA", "艾达币"),
    ("LINKUSDT", "LINK", "Chainlink"),
]
BINANCE_API = "https://api.binance.us/api/v3/klines"


def ema(values, span):
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def is_daily_run(now):
    """Daily summary run: 00:00-00:59 UTC (00:30 UTC schedule)."""
    if os.environ.get("CRYPTO_DAILY") == "1":
        return True
    return now.hour == 0


def fetch_closes(symbol):
    r = requests.get(BINANCE_API, params={"symbol": symbol,
                                           "interval": "1d", "limit": 100},
                     timeout=30)
    r.raise_for_status()
    return [float(k[4]) for k in r.json()]


def coin_signals(closes, daily):
    """Return (last, prev, pct, [signal strings]) for one coin."""
    last, prev = closes[-1], closes[-2]
    pct = (last / prev - 1) * 100
    signals = []
    if len(closes) > 20 and last > max(closes[-21:-1]):
        signals.append("突破20日高点")
    if daily:
        if len(closes) > 50:
            dif = [a - b for a, b in zip(ema(closes, 19), ema(closes, 39))]
            dea = ema(dif, 9)
            if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
                signals.append("MACD刚翻多")
    elif abs(pct) >= 5:
        signals.append("24小时大涨" if pct > 0 else "24小时大跌")
    return last, prev, pct, signals


def main():
    now = datetime.now(timezone.utc)
    daily = is_daily_run(now)
    rows = []
    for symbol, code, name in COINS:
        try:
            closes = fetch_closes(symbol)
            last, prev, pct, signals = coin_signals(closes, daily)
            rows.append((code, name, last, prev, pct, signals, None))
        except Exception as e:
            rows.append((code, name, None, None, None, [], str(e)))

    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# 加密货币监控（只看价格，不下单）", "", f"- 更新时间：{now_str}",
             "- 数据：Binance 公开接口（BTC/ETH/SOL/BNB/XRP/DOGE/ADA/LINK）",
             "- 信号说明：价格突破 20 日最高价，或 MACD 19/39/9 刚翻多，都算趋势刚启动，不保证涨，突破也可能回落；每 30 分钟更新一次",
             "", "| 代码 | 名称 | 最新价 | 24小时涨跌 | 信号 |",
             "| --- | --- | --- | --- | --- |"]
    alerts = []
    for code, name, last, prev, pct, signals, err in rows:
        if err is not None or last is None:
            lines.append(f"| {code} | {name} | 获取失败 | - | - |")
            continue
        sig = "、".join(signals) if signals else ""
        if signals:
            alerts.append(f"{code}（{sig}）")
        lines.append(f"| {code} | {name} | ${last:,.2f} | {pct:+.2f}% | {sig} |")
    lines.append("")
    if alerts:
        lines.append("## 提醒\n\n- 今日趋势刚启动：" + "，".join(alerts))
    else:
        lines.append("## 提醒\n\n- 今日无趋势启动信号。")
    lines.append("")
    lines.append("说明：价格是 Binance 公开行情，仅供参考，不是投资建议。")
    report = "\n".join(lines) + "\n"

    out_dir = os.environ.get("SIGNAL_OUT", "signals")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "crypto.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    state_path = os.path.join(out_dir, "crypto-alerts.json")
    previous = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                previous = {a["key"]: a for a in json.load(f).get("alerts", [])}
        except Exception:
            previous = {}
    new_alerts = []
    for key in alerts:
        entry = previous.get(key, {"key": key, "first_seen": now_str})
        new_alerts.append(entry)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"updated": now_str, "daily": daily,
                   "alerts": new_alerts}, f, ensure_ascii=False, indent=2)
    print(report)
    print("wrote", path, "and", state_path)


if __name__ == "__main__":
    main()
