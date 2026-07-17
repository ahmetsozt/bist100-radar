"""BIST100 fundamental data fetcher — Alphabet-style metrics per stock.

Outputs bist100_data.json with per-stock: quarterly revenue/net income trend,
balance sheet snapshot, cash flow (OCF/capex/FCF, TTM), annual revenue, ratios.
"""
import json
import math
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

warnings.filterwarnings("ignore")

TICKERS = ["AEFES", "AKBNK", "AKSA", "AKSEN", "ALARK", "ALTNY", "ANSGR", "ARCLK", "ASELS", "ASTOR", "BALSU", "BERA", "BIMAS", "BRSAN", "BRYAT", "BSOKE", "BTCIM", "CANTE", "CCOLA", "CIMSA", "CVKMD", "CWENE", "DAPGM", "DOAS", "DOHOL", "DSTKF", "ECILC", "EFOR", "EKGYO", "ENERY", "ENJSA", "ENKAI", "EREGL", "ESEN", "EUPWR", "EUREN", "FENER", "FROTO", "GARAN", "GENIL", "GESAN", "GLRMK", "GRSEL", "GRTHO", "GSRAY", "GUBRF", "HALKB", "HEKTS", "IEYHO", "ISCTR", "ISMEN", "IZENR", "KCHOL", "KLRHO", "KRDMD", "KTLEV", "KUYAS", "MAGEN", "MAVI", "MGROS", "MIATK", "MPARK", "OBAMS", "ODAS", "ODINE", "OTKAR", "OYAKC", "PAHOL", "PASEU", "PATEK", "PETKM", "PGSUS", "PSGYO", "QUAGR", "RALYH", "REEDR", "SAHOL", "SARKY", "SASA", "SISE", "SKBNK", "SOKM", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TRALT", "TRENJ", "TRMET", "TSKB", "TTKOM", "TUKAS", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESTL", "YKBNK", "ZOREN"]

N_QUARTERS = 6


def clean(v):
    """NaN/inf -> None, numpy -> float."""
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def row(df, *names):
    """First matching row from a statement DataFrame as {date: value}."""
    if df is None or df.empty:
        return {}
    for name in names:
        if name in df.index:
            s = df.loc[name]
            return {str(k.date()): clean(v) for k, v in s.items()}
    return {}


def latest(d):
    if not d:
        return None, None
    k = max(d)
    return k, d[k]


def series_desc(d, n=N_QUARTERS):
    """Last n periods, newest first, as [[date, value], ...]."""
    return [[k, d[k]] for k in sorted(d, reverse=True)[:n]]


def ttm(d):
    vals = [v for _, v in series_desc(d, 4) if v is not None]
    return sum(vals) if len(vals) == 4 else None


def fetch_one(code):
    t = yf.Ticker(code + ".IS")
    q_inc = t.quarterly_income_stmt
    q_bs = t.quarterly_balance_sheet
    q_cf = t.quarterly_cashflow
    a_inc = t.income_stmt

    rev = row(q_inc, "Total Revenue", "Operating Revenue")
    ni = row(q_inc, "Net Income", "Net Income Common Stockholders")
    op = row(q_inc, "Operating Income", "Pretax Income")

    a_rev = row(a_inc, "Total Revenue", "Operating Revenue")
    a_ni = row(a_inc, "Net Income", "Net Income Common Stockholders")

    ta = row(q_bs, "Total Assets")
    cash = row(q_bs, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
    tl = row(q_bs, "Total Liabilities Net Minority Interest")
    debt = row(q_bs, "Total Debt")
    eq = row(q_bs, "Stockholders Equity", "Total Equity Gross Minority Interest")

    ocf = row(q_cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = row(q_cf, "Capital Expenditure")

    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    fi = {}
    try:
        fi = dict(t.fast_info)
    except Exception:
        pass

    rev_s = series_desc(rev)
    ni_s = series_desc(ni)

    def yoy(s):
        if len(s) >= 5 and s[0][1] and s[4][1]:
            return (s[0][1] / s[4][1] - 1) * 100
        return None

    def qoq(s):
        if len(s) >= 2 and s[0][1] and s[1][1]:
            return (s[0][1] / s[1][1] - 1) * 100
        return None

    bs_date, ta_v = latest(ta)
    _, eq_v = latest(eq)
    _, debt_v = latest(debt)
    _, cash_v = latest(cash)
    _, tl_v = latest(tl)

    ocf_s = series_desc(ocf)
    capex_s = series_desc(capex)
    ocf_ttm, capex_ttm = ttm(ocf), ttm(capex)
    fcf_ttm = (ocf_ttm + capex_ttm) if (ocf_ttm is not None and capex_ttm is not None) else None
    ocf_q = ocf_s[0][1] if ocf_s else None
    capex_q = capex_s[0][1] if capex_s else None
    fcf_q = (ocf_q + capex_q) if (ocf_q is not None and capex_q is not None) else None

    ann = sorted(a_rev, reverse=True)[:2]
    a_rev_pairs = [[k, a_rev[k]] for k in ann]
    ann_growth = None
    if len(a_rev_pairs) == 2 and a_rev_pairs[0][1] and a_rev_pairs[1][1]:
        ann_growth = (a_rev_pairs[0][1] / a_rev_pairs[1][1] - 1) * 100

    ni_q = ni_s[0][1] if ni_s else None
    rev_q = rev_s[0][1] if rev_s else None

    return {
        "code": code,
        "name": info.get("longName") or info.get("shortName") or code,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": clean(fi.get("lastPrice") or info.get("currentPrice")),
        "marketCap": clean(fi.get("marketCap") or info.get("marketCap")),
        "revQ": rev_s,
        "niQ": ni_s,
        "opQ": series_desc(op),
        "revYoY": yoy(rev_s),
        "revQoQ": qoq(rev_s),
        "niYoY": yoy(ni_s),
        "netMargin": (ni_q / rev_q * 100) if (ni_q and rev_q) else None,
        "annualRev": a_rev_pairs,
        "annualNi": [[k, a_ni.get(k)] for k in ann],
        "annualRevGrowth": ann_growth,
        "bsDate": bs_date,
        "totalAssets": ta_v,
        "cash": cash_v,
        "totalLiab": tl_v,
        "totalDebt": debt_v,
        "equity": eq_v,
        "debtToEquity": (debt_v / eq_v) if (debt_v is not None and eq_v and eq_v > 0) else None,
        "ocfQ": ocf_s,
        "capexQ": capex_s,
        "ocfTtm": ocf_ttm,
        "capexTtm": capex_ttm,
        "fcfTtm": fcf_ttm,
        "fcfQ": fcf_q,
        "pe": clean(info.get("trailingPE")),
        "pb": clean(info.get("priceToBook")),
    }


def main():
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, c): c for c in TICKERS}
        for i, fut in enumerate(as_completed(futs), 1):
            code = futs[fut]
            try:
                results.append(fut.result())
                print(f"[{i}/{len(TICKERS)}] {code} ok", flush=True)
            except Exception as e:
                print(f"[{i}/{len(TICKERS)}] {code} FAIL {e}", flush=True)
                errors.append(code)

    # one retry round, sequential
    for code in list(errors):
        try:
            time.sleep(2)
            results.append(fetch_one(code))
            errors.remove(code)
            print(f"retry {code} ok", flush=True)
        except Exception as e:
            print(f"retry {code} FAIL {e}", flush=True)

    results.sort(key=lambda r: -(r["marketCap"] or 0))
    import datetime
    out = {"asOf": datetime.date.today().isoformat(), "count": len(results), "failed": errors, "stocks": results}
    with open("bist100_data.json", "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"DONE ok={len(results)} failed={errors}")


if __name__ == "__main__":
    main()
