"""Daily US-stock monitor: fetch the previous trading day's close for the
5 US stocks from the user's Gate screenshot (NVDA, AMD, MU, AVGO, TSLA)
via the public Yahoo Finance chart API (no key), plus SPCX (SpaceX token
on Gate) via Gate's public spot ticker API (no key). Writes a daily
report to signals/us-stocks.md and flags any stock that moved >= 5% in
a day. PRICE MONITORING ONLY - no orders, no API keys, no real money.
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
ALERT_PCT = 5.0


def fetch_yahoo(symbol):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, params={"range": "5d", "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
    last, prev = closes[-1], closes[-2]
    return last, prev


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
            last, prev = fetch_yahoo(symbol)
            rows.append((symbol, name, last, prev, None))
        except Exception as e:
            rows.append((symbol, name, None, None, str(e)))
    try:
        last, prev = fetch_spcx()
        rows.append(("SPCX", "SpaceX（Gate 代币）", last, prev, None))
    except Exception as e:
        rows.append(("SPCX", "SpaceX（Gate 代币）", None, None, str(e)))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# 美股每日监控（只看价格，不下单）", "", f"- 更新时间：{now}",
             "- 数据：Yahoo Finance（NVDA/AMD/MU/AVGO/TSLA）+ Gate 公开接口（SPCX）",
             "", "| 代码 | 名称 | 最新价 | 日涨跌 | 提醒 |",
             "| --- | --- | --- | --- | --- |"]
    alerts = []
    for symbol, name, last, prev, err in rows:
        if err is not None or last is None:
            lines.append(f"| {symbol} | {name} | 获取失败 | - | - |")
            continue
        pct = (last / prev - 1) * 100
        flag = "⚠️ 大涨跌" if abs(pct) >= ALERT_PCT else ""
        if flag:
            alerts.append(f"{symbol} {pct:+.2f}%")
        lines.append(f"| {symbol} | {name} | ${last:,.2f} | {pct:+.2f}% | {flag} |")
    lines.append("")
    if alerts:
        lines.append("## 提醒\n\n- 今日大涨跌（≥5%）：" + "，".join(alerts))
    else:
        lines.append("## 提醒\n\n- 今日无大涨跌（涨跌都在 5% 以内）。")
    lines.append("")
    lines.append("说明：价格是上一交易日收盘价附近的最新价，仅供参考，不是投资建议。SPCX 是 SpaceX 在 Gate 上的代币，不是上市公司股票。")
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
