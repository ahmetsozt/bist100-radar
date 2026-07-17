"""Teknik gösterge katmanı: 100 hisse + XU100 için 2 yıllık günlük OHLCV çekip
göstergeleri Python'da hesaplar; panoya yalnızca sonuçlar + 60 günlük mini seri gider.

Çıktı: technical.json  {asOf, market:{...}, stocks:{KOD:{...}}}
"""
import json
import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from fetch_bist100 import TICKERS

warnings.filterwarnings("ignore")

MONTH = 21  # işlem günü


def sig(v, n=4):
    """Yuvarlanmış float ya da None (payload küçük kalsın)."""
    try:
        f = float(v)
        if not math.isfinite(f):
            return None
        return float(f"{f:.{n}g}")
    except (TypeError, ValueError):
        return None


def rsi14(close):
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
    return 100 - 100 / (1 + gain / loss)


def crossed_within(a, b, bars):
    """a-b farkının son `bars` içinde işaret değiştirdiyse yönü: 1 yukarı, -1 aşağı, 0 yok."""
    diff = (a - b).dropna()
    if len(diff) < bars + 1:
        return 0
    tail = np.sign(diff.iloc[-(bars + 1):])
    changes = tail.diff().dropna()
    ups = (changes > 0).any()
    downs = (changes < 0).any()
    if ups and not downs:
        return 1
    if downs and not ups:
        return -1
    return 0


def ret(close, bars):
    if len(close) <= bars or close.iloc[-bars - 1] == 0:
        return None
    return (close.iloc[-1] / close.iloc[-bars - 1] - 1) * 100


def analyze(df, idx_ret3m, idx_daily=None):
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        return None
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    ema20 = c.ewm(span=20).mean()
    rsi = rsi14(c)
    ema12, ema26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = ema12 - ema26
    macds = macd.ewm(span=9).mean()
    hist = macd - macds
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14).mean()

    last = c.iloc[-1]
    hi52 = h.rolling(252, min_periods=60).max().iloc[-1]
    lo52 = l.rolling(252, min_periods=60).min().iloc[-1]
    r3 = ret(c, 3 * MONTH)
    rs3m = (r3 - idx_ret3m) if (r3 is not None and idx_ret3m is not None) else None

    beta = None
    if idx_daily is not None:
        rr = pd.concat([c.pct_change(), idx_daily], axis=1).dropna().tail(252)
        if len(rr) > 60 and rr.iloc[:, 1].var() > 0:
            beta = rr.iloc[:, 0].cov(rr.iloc[:, 1]) / rr.iloc[:, 1].var()

    s50, s200 = sma50.iloc[-1], sma200.iloc[-1]
    rsi_v, hist_v = rsi.iloc[-1], hist.iloc[-1]

    # şeffaf teknik puan (Metodoloji'de aynen yazılır): 0-6
    pts = 0
    if not math.isnan(s200) and last > s200: pts += 2
    if not math.isnan(s50) and last > s50: pts += 1
    if not math.isnan(rsi_v) and 45 <= rsi_v <= 70: pts += 1
    if not math.isnan(hist_v) and hist_v > 0: pts += 1
    if rs3m is not None and rs3m > 0: pts += 1
    direction = "up" if pts >= 4 else ("down" if pts <= 2 else "flat")

    n = 60
    tail = df.tail(n)
    return {
        "close": sig(last),
        "sma50": sig(s50), "sma200": sig(s200), "ema20": sig(ema20.iloc[-1]),
        "rsi": sig(rsi_v, 3),
        "macdHist": sig(hist_v, 3),
        "macdCross": crossed_within(macd, macds, 5),
        "goldenCross": crossed_within(sma50, sma200, 20),
        "atr": sig(atr.iloc[-1]),
        "atrPct": sig(atr.iloc[-1] / last * 100, 3) if last else None,
        "hi52": sig(hi52), "lo52": sig(lo52),
        "dHi52": sig((last / hi52 - 1) * 100, 3) if hi52 else None,
        "dLo52": sig((last / lo52 - 1) * 100, 3) if lo52 else None,
        "ret1m": sig(ret(c, MONTH), 3), "ret3m": sig(r3, 3), "ret6m": sig(ret(c, 6 * MONTH), 3),
        "rs3m": sig(rs3m, 3),
        "avgVolTL": sig((v * c).rolling(20).mean().iloc[-1], 3),
        "beta": sig(beta, 3),
        "swingLow": sig(l.tail(20).min()), "swingHigh": sig(h.tail(20).max()),
        "pts": pts, "dir": direction,
        # yalnızca 4 eksen etiketi (payload küçük kalsın)
        "ticks": [[i, tail.index[i].strftime("%d.%m")] for i in
                  sorted({0, len(tail) // 3, 2 * len(tail) // 3, len(tail) - 1})],
        "c60": [sig(x) for x in tail["Close"]],
        "s50_60": [sig(x) for x in sma50.tail(n)],
        "s200_60": [sig(x) for x in sma200.tail(n)],
    }


def main():
    symbols = [c + ".IS" for c in TICKERS] + ["XU100.IS"]
    raw = yf.download(symbols, period="2y", interval="1d",
                      group_by="ticker", progress=False, threads=True)

    idx = raw["XU100.IS"].dropna(subset=["Close"])
    idx_c = idx["Close"]
    idx_ret3m = ret(idx_c, 3 * MONTH)
    idx_daily = idx_c.pct_change()

    m = analyze(idx, idx_ret3m=None)
    regime = "bull" if (m and m["sma200"] and m["close"] > m["sma200"] and m["sma50"] and m["close"] > m["sma50"]) \
        else ("bear" if (m and m["sma200"] and m["close"] < m["sma200"]) else "flat")
    market = {"close": m["close"], "sma50": m["sma50"], "sma200": m["sma200"],
              "rsi": m["rsi"], "ret3m": m["ret3m"], "regime": regime} if m else {}

    stocks, fails = {}, []
    for code in TICKERS:
        try:
            r = analyze(raw[code + ".IS"], idx_ret3m, idx_daily)
            if r:
                # mini seri sadece grafiği besler; XU100 kıyası ayrı alanda
                stocks[code] = r
            else:
                fails.append(code)
        except Exception:
            fails.append(code)

    out = {"market": market, "stocks": stocks, "failed": fails}
    json.dump(out, open("technical.json", "w"))
    print(f"technical.json — {len(stocks)} hisse, rejim: {regime}, başarısız: {fails}")


if __name__ == "__main__":
    main()
