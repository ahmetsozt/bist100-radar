"""NUUK BIST Radar — Sinyal Motoru (Fable 5 döngüsü uyarlaması).

Boru hattı: TARA (technical.json hazır) -> SİNYAL (kurulum tespiti) -> PLAN
(ATR stop + 1R/2R/3R) -> RİSK (likidite/volatilite/rejim) -> KARAR (RADAR/İZLE/GEÇ).

Girdi:  technical.json, bist100_final.json
Çıktı:  signals.json   {asOf, market, counts, signals:[...]}

Tümü MEKANİK kural çıktısıdır — yatırım tavsiyesi değildir. Karar insana aittir.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda n: os.path.join(HERE, n)

MONTH = 21
LIQ_MIN_TL = 50_000_000      # 50 mn TL/gün altı likidite = bloke
ATR_MAX_PCT = 8.0            # günde >±%8 oynayan = aşırı volatil, bloke
ATR_K = 1.5                 # stop = giriş - K×ATR


def g(d, k, default=None):
    v = d.get(k)
    return v if v is not None else default


def pctl_maker(vals):
    a = sorted(v for v in vals if v is not None and math.isfinite(v))
    def f(v):
        if v is None or not math.isfinite(v) or not a:
            return 50.0
        lo = sum(1 for x in a if x < v)
        return lo / len(a) * 100
    return f


def fundamental_scores(stocks):
    """Panodaki JS skoruyla aynı harman: %30 büyüme + %25 marj + %25 FCF/gelir + %20 net nakit/varlık."""
    def op_margin(s):
        rq = s.get("revQ") or []
        if not rq or not rq[0][1]:
            return None
        d0 = rq[0][0]
        opv = next((v for dt, v in (s.get("opQ") or []) if dt == d0), None)
        return (opv / rq[0][1] * 100) if opv is not None else None

    def rev_ttm(s):
        rq = s.get("revQ") or []
        vs = [v for _, v in rq[:4] if v is not None]
        return sum(vs) if len(vs) == 4 else None

    def net_cash(s):
        c, d = s.get("cash"), s.get("totalDebt")
        return (c - d) if (c is not None and d is not None) else None

    pG = pctl_maker([s.get("revYoY") for s in stocks])
    pM = pctl_maker([op_margin(s) for s in stocks])
    pF = pctl_maker([(s.get("fcfTtm") / rev_ttm(s)) if (s.get("fcfTtm") is not None and rev_ttm(s)) else None for s in stocks])
    pB = pctl_maker([(net_cash(s) / s["totalAssets"]) if (net_cash(s) is not None and s.get("totalAssets")) else None for s in stocks])
    out = {}
    for s in stocks:
        rt = rev_ttm(s)
        fcf_r = (s.get("fcfTtm") / rt) if (s.get("fcfTtm") is not None and rt) else None
        nc = net_cash(s)
        nca = (nc / s["totalAssets"]) if (nc is not None and s.get("totalAssets")) else None
        out[s["code"]] = round(0.30 * pG(s.get("revYoY")) + 0.25 * pM(op_margin(s))
                               + 0.25 * pF(fcf_r) + 0.20 * pB(nca))
    return out


def detect(t):
    """Kurulumları puanla (confluence), en güçlüsünü döndür. -> (setup, strength, reasons) veya None."""
    close = g(t, "close"); sma50 = g(t, "sma50"); sma200 = g(t, "sma200")
    ema20 = g(t, "ema20"); rsi = g(t, "rsi"); hist = g(t, "macdHist", 0)
    mcross = g(t, "macdCross", 0); gcross = g(t, "goldenCross", 0)
    dHi = g(t, "dHi52"); dLo = g(t, "dLo52"); rs3 = g(t, "rs3m", 0)
    swH = g(t, "swingHigh"); rsi = rsi if rsi is not None else 50
    if close is None or sma50 is None or sma200 is None:
        return None
    aligned = close > sma50 > sma200
    cands = []

    # Kırılım
    r, sc = [], 0
    if swH and close >= swH * 0.995: sc += 30; r.append("20 günlük zirveyi test/kırıyor")
    if dHi is not None and dHi > -3: sc += 20; r.append("52 hafta zirvesine yakın")
    if 55 <= rsi <= 72: sc += 15; r.append(f"RSI güçlü ({rsi:.0f})")
    if hist and hist > 0: sc += 10; r.append("MACD pozitif")
    if rs3 and rs3 > 0: sc += 15; r.append("XU100 üstü relatif güç")
    cands.append(("Kırılım", sc, r))

    # Geri çekilme
    r, sc = [], 0
    if aligned: sc += 30; r.append("SMA50>SMA200 yükseliş dizilimi")
    if 40 <= rsi <= 55: sc += 25; r.append(f"RSI geri çekilme bölgesinde ({rsi:.0f})")
    if ema20 and close < ema20 and sma50 and close > sma50: sc += 15; r.append("EMA20 altına sarktı, SMA50 üstünde")
    if rs3 and rs3 > 0: sc += 15; r.append("XU100 üstü relatif güç")
    cands.append(("Geri çekilme", sc, r))

    # Momentum
    r, sc = [], 0
    if mcross == 1: sc += 30; r.append("MACD yukarı kesişimi (son 5 gün)")
    if 50 <= rsi <= 70: sc += 20; r.append(f"RSI momentum bölgesinde ({rsi:.0f})")
    if hist and hist > 0: sc += 15; r.append("MACD histogramı pozitif")
    if sma50 and close > sma50: sc += 15; r.append("Fiyat SMA50 üstünde")
    if rs3 and rs3 > 0: sc += 10; r.append("XU100 üstü relatif güç")
    cands.append(("Momentum", sc, r))

    # Trend devamı
    r, sc = [], 0
    if aligned: sc += 35; r.append("Fiyat > SMA50 > SMA200")
    if 45 <= rsi <= 68: sc += 20; r.append(f"RSI sağlıklı ({rsi:.0f})")
    if rs3 and rs3 > 0: sc += 15; r.append("XU100 üstü relatif güç")
    if gcross == 1: sc += 15; r.append("Golden cross (son 20 gün)")
    if hist and hist > 0: sc += 10; r.append("MACD pozitif")
    cands.append(("Trend devamı", sc, r))

    # Dönüş (riskli, tavan düşük)
    r, sc = [], 0
    if dLo is not None and dLo < 12: sc += 25; r.append("52 hafta dibine yakın")
    if 30 <= rsi <= 48: sc += 20; r.append(f"RSI dipten dönüyor ({rsi:.0f})")
    if mcross == 1: sc += 15; r.append("MACD yukarı kesişimi")
    if ema20 and close > ema20: sc += 10; r.append("EMA20 üstüne çıktı")
    cands.append(("Dönüş", min(sc, 65), r))  # dönüş kurulumları tavanlı

    setup, strength, reasons = max(cands, key=lambda c: c[1])
    return (setup, strength, reasons) if strength >= 50 else None


def main():
    tech = json.load(open(p("technical.json")))
    fin = json.load(open(p("bist100_final.json")))
    fscores = fundamental_scores(fin["stocks"])
    names = {s["code"]: s.get("name", s["code"]) for s in fin["stocks"]}
    SEC_TR = {"Financial Services": "Finans", "Industrials": "Sanayi", "Consumer Cyclical": "Tüketim",
              "Consumer Defensive": "Temel Tüketim", "Basic Materials": "Temel Malzemeler", "Energy": "Enerji",
              "Utilities": "Kamu", "Technology": "Teknoloji", "Communication Services": "İletişim",
              "Real Estate": "Gayrimenkul", "Healthcare": "Sağlık"}
    sectors = {s["code"]: SEC_TR.get(s.get("sector"), s.get("sector") or "—") for s in fin["stocks"]}
    regime = (tech.get("market") or {}).get("regime", "flat")

    sig = []
    for code, t in (tech.get("stocks") or {}).items():
        d = detect(t)
        if not d:
            continue
        setup, strength, reasons = d
        close = t["close"]; atr = g(t, "atr"); atrPct = g(t, "atrPct")
        swL = g(t, "swingLow"); vol = g(t, "avgVolTL", 0)

        # RİSK kapısı
        risk_flags = []
        blocked = False
        if not vol or vol < LIQ_MIN_TL:
            blocked = True; risk_flags.append("Düşük likidite")
        if atrPct is not None and atrPct > ATR_MAX_PCT:
            blocked = True; risk_flags.append("Aşırı volatilite")
        # rejim: ayı piyasasında long kurulumları zayıflat
        adj = strength
        if regime == "bear":
            adj -= 20; risk_flags.append("Piyasa rejimi AYI")
        elif regime == "flat":
            adj -= 5

        # PLAN
        if not atr:
            continue
        stop = round(close - ATR_K * atr, 2)          # ATR bazlı stop (tutarlı risk = K×ATR%)
        struct = round(swL * 0.995, 2) if swL else None  # yapısal destek referansı (bilgi amaçlı)
        if stop >= close:
            continue
        rper = close - stop
        targets = [round(close + m * rper, 2) for m in (1, 2, 3)]
        fscore = fscores.get(code, 50)

        # KARAR
        if blocked:
            decision = "GEÇ"
        elif adj >= 70 and fscore >= 55:
            decision = "RADAR"
        elif adj >= 55:
            decision = "İZLE"
        else:
            decision = "GEÇ"
        if decision == "GEÇ":
            continue  # yalnızca RADAR/İZLE yayınlanır

        sig.append({
            "code": code, "name": names.get(code, code), "sector": sectors.get(code, "—"),
            "setup": setup, "dir": "long", "strength": int(round(adj)),
            "fscore": fscore, "decision": decision,
            "entry": round(close, 2), "stop": stop, "struct": struct,
            "t1": targets[0], "t2": targets[1], "t3": targets[2],
            "riskPct": round(rper / close * 100, 1),
            "atrPct": round(atrPct, 1) if atrPct is not None else None,
            "volTL": vol,
            "reasons": reasons[:4], "riskFlags": risk_flags,
        })

    sig.sort(key=lambda x: (x["decision"] != "RADAR", -x["strength"]))
    out = {
        "asOf": fin.get("asOf"),
        "market": {"regime": regime},
        "counts": {"radar": sum(1 for x in sig if x["decision"] == "RADAR"),
                   "izle": sum(1 for x in sig if x["decision"] == "İZLE"),
                   "total": len(sig)},
        "signals": sig,
    }
    json.dump(out, open(p("signals.json"), "w"), ensure_ascii=False)
    print(f"signals.json — {out['counts']['radar']} RADAR, {out['counts']['izle']} İZLE, rejim: {regime}")


if __name__ == "__main__":
    main()
