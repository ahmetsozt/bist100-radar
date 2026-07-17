"""Post-process bist100_data.json (CI-friendly):
- convert USD/EUR reporters to TRY at live FX (reporter list cached in currencies.json)
- recompute YoY/QoQ with date-matched quarters (yfinance series can have gaps)
Writes bist100_final.json
"""
import json
import warnings

import yfinance as yf

warnings.filterwarnings("ignore")

d = json.load(open("bist100_data.json"))
CURRENCIES = json.load(open("currencies.json"))  # code -> "USD"/"EUR"; rest assumed TRY

fx = {"TRY": 1.0}
for pair in ("USDTRY=X", "EURTRY=X"):
    h = yf.Ticker(pair).history(period="5d")["Close"]
    fx[pair[:3]] = float(h.iloc[-1])
print("FX:", {k: round(v, 2) for k, v in fx.items()})

SCALARS = ["totalAssets", "cash", "totalLiab", "totalDebt", "equity",
           "ocfTtm", "capexTtm", "fcfTtm", "fcfQ"]
SERIES = ["revQ", "niQ", "opQ", "annualRev", "annualNi", "ocfQ", "capexQ"]


def month_index(iso):
    return int(iso[:4]) * 12 + int(iso[5:7])


def matched_growth(series, months_back, tol=1):
    """% change between newest point and the point ~months_back earlier."""
    if not series or series[0][1] in (None, 0):
        return None
    base_mi = month_index(series[0][0]) - months_back
    for dt, v in series[1:]:
        if abs(month_index(dt) - base_mi) <= tol:
            # growth only meaningful when base is positive (NI may flip sign)
            if v is None or v <= 0:
                return None
            return (series[0][1] / v - 1) * 100
    return None


for s in d["stocks"]:
    cur = CURRENCIES.get(s["code"], "TRY")
    s["finCurrency"] = cur
    r = fx.get(cur, 1.0)
    if r != 1.0:
        for k in SCALARS:
            if s.get(k) is not None:
                s[k] = s[k] * r
        for k in SERIES:
            s[k] = [[dt, (v * r if v is not None else None)] for dt, v in (s.get(k) or [])]
    s["revYoY"] = matched_growth(s["revQ"], 12)
    s["revQoQ"] = matched_growth(s["revQ"], 3)
    s["niYoY"] = matched_growth(s["niQ"], 12)

d["stocks"].sort(key=lambda r: -(r["marketCap"] or 0))
d["fx"] = {"USD": fx["USD"], "EUR": fx["EUR"]}
json.dump(d, open("bist100_final.json", "w"), ensure_ascii=False)
print("bist100_final.json yazıldı,", len(d["stocks"]), "hisse")
