"""Makro varlık katmanı: ons altın, gram altın, USD/TRY, EUR/TRY.

Gram altın hiçbir borsada TL cinsinden kote edilmediği için ons altın (USD) ve
USD/TRY'den türetilir:  gram_TL = ons_USD / 31.1034768 * USDTRY

Vadeli altın ile FX farklı takvimlerde işlem gördüğü için seriler ortak bir
tarih eksenine hizalanır ve ileri doldurulur; aksi halde gram altın serisinde
boşluklar oluşur.

Çıktı: macro.json  {asOf, assets: [{key, label, unit, last, chg1d, chg1m, chg1y, c60, ticks}]}
"""
import datetime
import json
import math
import warnings
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

TROY_OUNCE_G = 31.1034768   # 1 ons = 31,1034768 gram
SERIES_DAYS = 60            # mini grafik uzunluğu
MONTH = 21                  # işlem günü
YEAR = 252

SYMBOLS = {"ons": "GC=F", "usdtry": "USDTRY=X", "eurtry": "EURTRY=X"}


def sig(v, n=6):
    """Yuvarlanmış float ya da None (payload küçük kalsın)."""
    try:
        f = float(v)
        if not math.isfinite(f):
            return None
        return float(f"{f:.{n}g}")
    except (TypeError, ValueError):
        return None


def change_pct(s, bars):
    """`bars` işlem günü öncesine göre yüzde değişim."""
    if len(s) <= bars:
        return None
    base = s.iloc[-bars - 1]
    if not base:
        return None
    return (s.iloc[-1] / base - 1) * 100


def build_asset(key, label, unit, series, decimals, quote_date=None):
    """`series` yalnızca gerçek baskılar içermeli (ileri doldurulmuş değil):
    aksi halde veri gelmeyen günler %0,0 değişim gibi görünür."""
    s = series.dropna()
    if len(s) < 30:
        return None
    tail = s.tail(SERIES_DAYS)
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "decimals": decimals,
        "last": sig(s.iloc[-1]),
        # kotasyonun ait olduğu gün — türev varlıkta en bayat girdi belirler
        "date": (quote_date or s.index[-1]).strftime("%Y-%m-%d"),
        "chg1d": sig(change_pct(s, 1), 3),
        "chg1m": sig(change_pct(s, MONTH), 3),
        "chg1y": sig(change_pct(s, YEAR), 3),
        "c60": [sig(x) for x in tail],
        "ticks": [[i, tail.index[i].strftime("%d.%m")] for i in
                  sorted({0, len(tail) // 2, len(tail) - 1})],
    }


def close_frame():
    """Tüm sembolleri tek indirmede çekip ham kapanış tablosunu döndürür."""
    raw = yf.download(list(SYMBOLS.values()), period="2y", interval="1d",
                      group_by="ticker", progress=False, threads=True)
    cols = {}
    for key, sym in SYMBOLS.items():
        try:
            cols[key] = raw[sym]["Close"]
        except KeyError:
            print(f"uyarı: {sym} ({key}) çekilemedi")
    return pd.DataFrame(cols).dropna(how="all")


def main():
    df = close_frame()
    missing = [k for k in SYMBOLS if k not in df.columns]
    if missing:
        raise SystemExit(f"makro veri eksik: {missing}")

    # Gram altın türev: iki girdi de gerekli → yalnızca ikisinin de bastığı günler.
    # Değişim yüzdeleri ham serilerden hesaplanır; ileri doldurma tek yerde,
    # gram altının kendi ekseninde kalır ve orada da ortak günlerle sınırlıdır.
    pair = df[["ons", "usdtry"]].dropna(how="any")
    gram = pair["ons"] / TROY_OUNCE_G * pair["usdtry"]

    assets = [
        build_asset("gramAltin", "Gram Altın", "₺", gram, 2),
        build_asset("onsAltin", "Ons Altın", "$", df["ons"], 2),
        build_asset("usdtry", "USD/TRY", "₺", df["usdtry"], 4),
        build_asset("eurtry", "EUR/TRY", "₺", df["eurtry"], 4),
    ]
    assets = [a for a in assets if a]

    now = datetime.datetime.now(ZoneInfo("Europe/Istanbul"))
    out = {"asOf": now.strftime("%d.%m.%Y %H:%M"), "assets": assets}
    json.dump(out, open("macro.json", "w"))
    print(f"macro.json — {len(assets)} varlık: " +
          ", ".join(f"{a['label']} {a['last']}{a['unit']}" for a in assets))


if __name__ == "__main__":
    main()
