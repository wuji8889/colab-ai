"""Daily BTC signal + paper trading: fetch BTC/USDT daily bars (public
Binance US API, no key), compute dual-MA 10/20 and MACD 19/39/9 signals,
and simulate orders on a virtual $10,000 account driven by the 10/20
signal (buy all cash on 持有, sell all BTC on 空仓, 0.1% fee per trade).
SIGNAL + PAPER TRADING ONLY - places no real orders, holds no API keys.
State lives in signals/paper-portfolio.json, committed back to the repo.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

SYMBOL = "BTCUSDT"
LIMIT = 1000
API = "https://api.binance.us/api/v3/klines"
START_CASH = 10000.0
FEE = 0.001


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


def load_state(out_dir, price, date):
    path = os.path.join(out_dir, "paper-portfolio.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f), path
    state = {
        "start_cash": START_CASH,
        "start_price": price,
        "start_date": date,
        "cash": START_CASH,
        "btc": 0.0,
        "trades": [],
    }
    return state, path


def paper_trade(state, s):
    """Apply the 10/20 signal to the virtual account. Returns a trade
    description string, or None when nothing changed."""
    price = s["close"]
    date = s["date"]
    if s["ma_signal"] == "持有" and state["btc"] == 0 and state["cash"] > 0:
        btc = state["cash"] * (1 - FEE) / price
        spent = state["cash"]
        state["btc"] = btc
        state["cash"] = 0.0
        state["trades"].append(
            {"date": date, "side": "买入", "price": price,
             "btc": round(btc, 6), "cash": round(spent, 2)})
        return f"虚拟买入：{date} 以 ${price:,.2f} 全仓买入 {btc:.6f} BTC"
    if s["ma_signal"] == "空仓" and state["btc"] > 0:
        proceeds = state["btc"] * price * (1 - FEE)
        sold = state["btc"]
        state["cash"] = proceeds
        state["btc"] = 0.0
        state["trades"].append(
            {"date": date, "side": "卖出", "price": price,
             "btc": round(sold, 6), "cash": round(proceeds, 2)})
        return f"虚拟卖出：{date} 以 ${price:,.2f} 全部卖出 {sold:.6f} BTC"
    return None


def main():
    df = fetch_bars()
    s = signals(df)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out_dir = os.environ.get("SIGNAL_OUT", "signals")
    os.makedirs(out_dir, exist_ok=True)

    state, state_path = load_state(out_dir, s["close"], s["date"])
    trade_note = paper_trade(state, s)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    total = state["cash"] + state["btc"] * s["close"]
    total_ret = (total / state["start_cash"] - 1) * 100
    hold_value = state["start_cash"] / state["start_price"] * s["close"]
    hold_ret = (hold_value / state["start_cash"] - 1) * 100
    last_trade = state["trades"][-1] if state["trades"] else None
    last_line = (
        f"最近一次：{last_trade['date']} {last_trade['side']} "
        f"${last_trade['price']:,.2f}" if last_trade else "最近一次：无交易")
    action_line = trade_note if trade_note else "今日无操作：信号没变，虚拟账户不动。"

    report = f"""# BTC 每日信号（只算信号 + 虚拟下单，不动真钱）

- 更新时间：{now}
- 数据：{SYMBOL} 日线，{s['bars']} 根（{s['first_date']} 至 {s['date']}），收盘价 ${s['close']:,.2f}
- 双均线 10/20：MA10 ${s['ma10']:,.2f}，MA20 ${s['ma20']:,.2f}，信号：**{s['ma_signal']}**
- MACD 19/39/9：DIF {s['macd_dif']:,.2f}，DEA {s['macd_dea']:,.2f}，信号：**{s['macd_signal']}**

## 虚拟账户（本金 ${state['start_cash']:,.0f}，从 {state['start_date']} 开始）

- 现金 ${state['cash']:,.2f}，持仓 {state['btc']:.6f} BTC，总值 ${total:,.2f}，收益 {total_ret:+.2f}%
- 一直拿着到现在：${hold_value:,.2f}，收益 {hold_ret:+.2f}%
- 交易次数：{len(state['trades'])} 次，{last_line}
- {action_line}

说明：虚拟下单按 10/20 均线信号全仓进出，手续费 0.1%。回测里这两个策略都没跑赢一直拿着，信号仅供参考，不是投资建议。
"""
    path = os.path.join(out_dir, "daily-signal.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print("wrote", path, "and", state_path)


if __name__ == "__main__":
    main()
