"""Daily BTC signal job: fetch BTC/USDT daily bars (public Binance US API,
no key), compute dual-MA 10/20 and MACD 19/39/9 signals, write a markdown
report. SIGNAL ONLY - places no orders, holds no API keys.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

SYMBOL = "BTCUSDT"
LIMIT = 1000
API = "https://api.binance.us/api/v3/klines"


def fetch_bars():
    params = {"symbol": SYMBOL, "interval": "1d", "limit": LIMIT}
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    raw = r.json()
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    df["date"] = pd.to_datetime(df["close_time"], unit="ms", utc=True).dt.date
    df["close"] = df["close"].astype(float)
    return df[["date", "close"]]


def signals(df):
    close = df["close"]
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    # MACD 19/39/9, EMA with warm-up: values before bar 39 are unreliable,
    # so only the latest (well past warm-up) is used.
    ema_fast = close.ewm(span=19, adjust=False).mean()
    ema_slow = close.ewm(span=39, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=9, adjust=False).mean()
    last = df.iloc[-1]
    return {
        "date": str(last["date"]),
        "close": float(last["close"]),
        "ma10": float(ma10.iloc[-1]),
        "ma20": float(ma20.iloc[-1]),
        "ma_signal": "持有" if ma10.iloc[-1] > ma20.iloc[-1] else "空仓",
        "macd_dif": float(dif.iloc[-1]),
        "macd_dea": float(dea.iloc[-1]),
        "macd_signal": "持有" if dif.iloc[-1] > dea.iloc[-1] else "空仓",
        "bars": len(df),
        "first_date": str(df.iloc[0]["date"]),
    }


def main():
    df = fetch_bars()
    s = signals(df)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = f"""# BTC 每日信号（只算信号，不下单）

- 更新时间：{now}
- 数据：{SYMBOL} 日线，{s['bars']} 根（{s['first_date']} 至 {s['date']}），收盘价 ${s['close']:,.2f}
- 双均线 10/20：MA10 ${s['ma10']:,.2f}，MA20 ${s['ma20']:,.2f}，信号：**{s['ma_signal']}**
- MACD 19/39/9：DIF {s['macd_dif']:,.2f}，DEA {s['macd_dea']:,.2f}，信号：**{s['macd_signal']}**

说明：回测里这两个策略都没跑赢一直拿着，信号仅供参考，不是投资建议。
"""
    out_dir = os.environ.get("SIGNAL_OUT", "signals")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "daily-signal.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print("wrote", path)


if __name__ == "__main__":
    main()
