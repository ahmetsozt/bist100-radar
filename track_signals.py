"""NUUK BIST Radar — Sinyal Takip Katmanı (canlı fiyat + sonuç izleme).

compute_signals.py taze kurulumları (günlük bar) üretir; bu katman onları KALICI
olarak izler:
  • Yeni kurulum -> canlı fiyattan giriş/stop/hedef sabitlenir, "aktif" açılır.
  • Aktif sinyal -> her saat canlı fiyat kontrol edilir; hedef/stop görüldüyse
    "tamamlandı" olarak DONDURULUR (giriş/stop/hedef değişmez), sonuç (+1R/+2R/+3R
    ya da STOP) kartta gösterilir. Tamamlananlar 48 saat sergilenir.
  • Kurulumu bozulan (artık aday olmayan) ve hedef/stop görmeyen sinyal -> "geçersiz",
    listeden kaldırılır.
Piyasa kapalıyken yeni sinyal ÜRETİLMEZ ve bayat fiyat gösterilmez (donar).

Kalıcı durum: signal_log.json  (repoya commit edilir)
Site çıktısı: signals.json      (build_site.py gömer)
"""
import json
import math
import os
import warnings
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda n: os.path.join(HERE, n)

IST = ZoneInfo("Europe/Istanbul")
MAX_AGE_MIN = 45           # canlı fiyat bu kadar dk'dan eskiyse bayat
DONE_RETAIN_H = 48         # tamamlanan sinyal kaç saat sergilenir


def now_ist():
    return datetime.now(IST)


def market_open(now):
    if now.weekday() >= 5:
        return False
    return dtime(10, 0) <= now.time() <= dtime(18, 15)


def fetch_live(codes):
    """Toplu canlı fiyat. -> {code: {"px":float,"hi":float,"lo":float,"fresh":bool}}."""
    out = {}
    if not codes:
        return out
    try:
        import yfinance as yf
        syms = [c + ".IS" for c in codes]
        raw = yf.download(syms, period="1d", interval="1m",
                          group_by="ticker", progress=False, threads=True)
        now_utc = datetime.now(timezone.utc)
        for c in codes:
            try:
                df = raw[c + ".IS"].dropna(subset=["Close"]) if len(codes) > 1 else raw.dropna(subset=["Close"])
                if df is None or not len(df):
                    out[c] = {"px": None, "hi": None, "lo": None, "fresh": False}
                    continue
                ts = df.index[-1].to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (now_utc - ts.astimezone(timezone.utc)).total_seconds() / 60
                out[c] = {
                    "px": float(df["Close"].iloc[-1]),
                    "hi": float(df["High"].max()),
                    "lo": float(df["Low"].min()),
                    "fresh": 0 <= age <= MAX_AGE_MIN,
                }
            except Exception:
                out[c] = {"px": None, "hi": None, "lo": None, "fresh": False}
    except Exception as e:
        print("canlı fiyat toplu çekim hatası:", e)
    return out


def plan_from(entry, risk_pct):
    rp = risk_pct / 100
    return {
        "entry": round(entry, 2),
        "stop": round(entry * (1 - rp), 2),
        "t1": round(entry * (1 + rp), 2),
        "t2": round(entry * (1 + 2 * rp), 2),
        "t3": round(entry * (1 + 3 * rp), 2),
    }


def main():
    now = now_ist()
    iso = now.isoformat(timespec="seconds")
    is_open = market_open(now)

    fresh = json.load(open(p("signals.json")))           # compute_signals çıktısı (aday kurulumlar)
    candidates = {s["code"]: s for s in fresh.get("signals", [])}

    log = {}
    if os.path.exists(p("signal_log.json")):
        try:
            log = json.load(open(p("signal_log.json")))
        except Exception:
            log = {}

    # İzlenecek kodlar: aktif olanlar + taze adaylar
    active_codes = {e["code"] for e in log.values() if e.get("status") == "active"}
    live = fetch_live(sorted(active_codes | set(candidates)))

    # 1) Mevcut AKTİF sinyalleri güncelle / kapat
    for sid, e in list(log.items()):
        if e.get("status") != "active":
            continue
        lv = live.get(e["code"], {})
        px, hi, lo, ok = lv.get("px"), lv.get("hi"), lv.get("lo"), lv.get("fresh")
        if not ok or px is None:
            e["stale"] = True            # canlı doğrulanamadı: bayat fiyat GÖSTERME (kart soluk)
            continue
        e["stale"] = False
        e["lastPrice"] = round(px, 2)
        e["updatedAt"] = iso
        e["maxSeen"] = max(e.get("maxSeen", e["entry"]), hi if hi is not None else px)
        e["minSeen"] = min(e.get("minSeen", e["entry"]), lo if lo is not None else px)

        # SONUÇ: ilk görülen hedef/stop dondurulur (hedefe öncelik: kâr realize varsayımı)
        reached = 3 if e["maxSeen"] >= e["t3"] else 2 if e["maxSeen"] >= e["t2"] else 1 if e["maxSeen"] >= e["t1"] else 0
        stopped = e["minSeen"] <= e["stop"]
        if reached:
            e["status"] = f"target{reached}"
            e["resultR"] = reached
            e["closedAt"] = iso
            e["closePrice"] = e["lastPrice"]
        elif stopped:
            e["status"] = "stopped"
            e["resultR"] = -1
            e["closedAt"] = iso
            e["closePrice"] = e["lastPrice"]
        else:
            # hâlâ aktif: kurulum geçerliliğini koru
            if e["code"] in candidates:
                c = candidates[e["code"]]  # meta tazele (giriş/stop/hedef SABİT kalır)
                e["strength"] = c["strength"]; e["fscore"] = c["fscore"]
                e["decision"] = c["decision"]; e["reasons"] = c.get("reasons", [])
                e["atrPct"] = c.get("atrPct"); e["riskFlags"] = c.get("riskFlags", [])
            elif is_open:
                e["status"] = "expired"    # kurulum bozuldu + hedef/stop yok -> kaldır
                e["closedAt"] = iso
            # piyasa kapalıysa aktif bırak (donmuş, canlı fiyat aranmaz)

    # 2) Yeni adayları aç (yalnızca piyasa açıkken, canlı fiyat tazeyse)
    if is_open:
        for code, c in candidates.items():
            if any(e["code"] == code and e.get("status") == "active" for e in log.values()):
                continue  # zaten izlenen aktif trade
            lv = live.get(code, {})
            if not lv.get("fresh") or lv.get("px") is None:
                continue  # canlı fiyat yoksa AÇMA (bayat sinyal üretme)
            pl = plan_from(lv["px"], c["riskPct"])
            sid = f'{code}#{iso}'
            log[sid] = {
                "code": code, "name": c["name"], "sector": c.get("sector", "—"),
                "setup": c["setup"], "decision": c["decision"], "strength": c["strength"],
                "fscore": c["fscore"], "riskPct": c["riskPct"], "atrPct": c.get("atrPct"),
                "reasons": c.get("reasons", []), "riskFlags": c.get("riskFlags", []),
                **pl, "lastPrice": round(lv["px"], 2),
                "maxSeen": lv["px"], "minSeen": lv["px"],
                "status": "active", "stale": False,
                "firstSeen": iso, "updatedAt": iso,
            }

    # 3) Süresi dolanları temizle (geçersiz -> hemen; tamamlanan -> 48s sonra)
    cutoff = (now - timedelta(hours=DONE_RETAIN_H)).isoformat(timespec="seconds")
    for sid in list(log):
        e = log[sid]
        if e["status"] == "expired":
            del log[sid]
        elif e["status"] in ("target1", "target2", "target3", "stopped") and e.get("closedAt", "") < cutoff:
            del log[sid]

    json.dump(log, open(p("signal_log.json"), "w"), ensure_ascii=False)

    # 4) Site görünümü: aktif (yeni en üstte) + tamamlanan (yeni kapanan üstte)
    entries = list(log.values())
    active = sorted([e for e in entries if e["status"] == "active"],
                    key=lambda e: e["firstSeen"], reverse=True)
    done = sorted([e for e in entries if e["status"] != "active"],
                  key=lambda e: e.get("closedAt", ""), reverse=True)
    view = active + done

    counts = {
        "radar": sum(1 for e in active if e["decision"] == "RADAR"),
        "izle": sum(1 for e in active if e["decision"] == "İZLE"),
        "active": len(active),
        "done": len(done),
        "total": len(view),
    }
    out = {
        "asOf": fresh.get("asOf"),
        "market": fresh.get("market", {}),
        "marketOpen": is_open,
        "counts": counts,
        "signals": view,
    }
    json.dump(out, open(p("signals.json"), "w"), ensure_ascii=False)
    print(f"track_signals — aktif {counts['active']} (RADAR {counts['radar']}), "
          f"tamamlanan {counts['done']}, piyasa {'AÇIK' if is_open else 'KAPALI'}")


if __name__ == "__main__":
    main()
