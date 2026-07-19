"""NUUK BIST Radar — Telegram sinyal iletimi (Fable 5 döngüsünün İLET halkası).

Yalnızca YENİ RADAR sinyallerini gönderir (saatlik spam olmaz): önceki gönderim
durumu signals_sent.json'da tutulur, sadece listeye yeni giren kurulumlar iletilir.

Ortam değişkenleri (GitHub Actions secret):
  TELEGRAM_TOKEN  bot token
  TELEGRAM_CHAT   hedef chat/kanal id
İkisi de yoksa sessizce atlanır (pano yine de güncellenir).
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda n: os.path.join(HERE, n)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
# NUUK Quant grubu + "Sinyaller" topic'i (gizli değil; erişim yalnızca bot token'ıyla)
CHAT = os.environ.get("TELEGRAM_CHAT") or "-1002388620539"
THREAD = os.environ.get("TELEGRAM_THREAD") or "2299"

IST = ZoneInfo("Europe/Istanbul")
MAX_AGE_MIN = 45          # canlı fiyat bu kadar dakikadan eskiyse bayat sayılır
MAX_DRIFT_PCT = 15        # canlı fiyat hesaplanan girişten bu kadar saparsa şüpheli, atla


def market_open_now():
    """BIST açık mı? Hafta içi 10:00–18:15 (İstanbul). (Tatiller fiyat tazeliğiyle elenir.)"""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False, "hafta sonu"
    if not (dtime(10, 0) <= now.time() <= dtime(18, 15)):
        return False, "seans dışı"
    return True, ""


def live_price(code):
    """Canlı fiyat + tazelik. -> (price, fresh_bool). yfinance BIST intraday ~15 dk gecikebilir."""
    try:
        import yfinance as yf
        h = yf.Ticker(code + ".IS").history(period="1d", interval="1m")
        if h is None or not len(h):
            return None, False
        px = float(h["Close"].iloc[-1])
        ts = h.index[-1].to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds() / 60
        fresh = 0 <= age_min <= MAX_AGE_MIN and math_ok(px)
        return px, fresh
    except Exception as e:
        print(f"  canlı fiyat hatası {code}: {e}")
        return None, False


def math_ok(v):
    return v is not None and v > 0


def tr(v, d=2):
    return ("{:,." + str(d) + "f}").format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": "true"}
    if THREAD and str(THREAD) != "0":
        payload["message_thread_id"] = THREAD
    data = urllib.parse.urlencode(payload).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return r.status


def build_msg(s, live_px, asof):
    """Canlı fiyattan planı tazele (aynı R yapısı korunur), mesajı kur."""
    rp = s["riskPct"] / 100
    entry = round(live_px, 2)
    stop = round(entry * (1 - rp), 2)
    t1 = round(entry * (1 + rp), 2)
    t2 = round(entry * (1 + 2 * rp), 2)
    t3 = round(entry * (1 + 3 * rp), 2)
    return (
        f"📡 <b>NUUK BIST Radar</b> — yeni sinyal\n"
        f"🟢 <b>{s['code']}</b> · {s['setup']} · güç {s['strength']}/100\n\n"
        f"Yön: LONG\n"
        f"Giriş: ₺{tr(entry)} <i>(canlı)</i>\n"
        f"Stop: ₺{tr(stop)} (−%{tr(s['riskPct'], 1)})\n"
        f"Hedefler: 1R ₺{tr(t1)} · 2R ₺{tr(t2)} · 3R ₺{tr(t3)}\n"
        f"Temel skor: {s['fscore']}/100\n\n"
        + "".join(f"✓ {r}\n" for r in s.get("reasons", [])[:3])
        + f"\n<i>{asof}</i>\n"
        f"⚠️ Mekanik kurulum tespitidir; yatırım tavsiyesi değildir. Karar sizindir."
    )


def main():
    sig = json.load(open(p("signals.json")))
    radar = [s for s in sig.get("signals", []) if s["decision"] == "RADAR"]
    cur_keys = {f'{s["code"]}|{s["setup"]}' for s in radar}

    sent = set()
    if os.path.exists(p("signals_sent.json")):
        try:
            sent = set(json.load(open(p("signals_sent.json"))))
        except Exception:
            pass
    new = [s for s in radar if f'{s["code"]}|{s["setup"]}' not in sent]

    # --- KAPI 1: yalnızca hafta içi + BIST açık saatleri ---
    open_ok, reason = market_open_now()
    if not open_ok:
        print(f"borsa kapalı ({reason}) — Telegram atlanıyor; sinyaller açılışa dek beklemede")
        return  # signals_sent DEĞİŞTİRİLMEZ: açılınca gönderilsinler
    if not new:
        print("yeni RADAR sinyali yok, Telegram atlanıyor")
        # sent'i güncel RADAR ile buda (kaybolanlar tekrar gelirse yeniden uyarır)
        json.dump(sorted(sent & cur_keys), open(p("signals_sent.json"), "w"), ensure_ascii=False)
        return
    if not (TOKEN and CHAT):
        print(f"{len(new)} yeni sinyal var ama TELEGRAM_TOKEN tanımlı değil — atlanıyor")
        return

    asof = sig.get("asOf", "")
    delivered = set()
    for s in new:
        # --- KAPI 2: fiyat kesinlikle güncel mi? ---
        px, fresh = live_price(s["code"])
        if not fresh:
            print(f"  {s['code']}: fiyat güncel değil (bayat/erişilemez) — atlanıyor, sonraki saat denenir")
            continue
        drift = abs(px / s["entry"] - 1) * 100 if s.get("entry") else 0
        if drift > MAX_DRIFT_PCT:
            print(f"  {s['code']}: canlı fiyat hesaptan %{drift:.0f} sapmış — şüpheli, atlanıyor")
            continue
        try:
            send(build_msg(s, px, asof))
            delivered.add(f'{s["code"]}|{s["setup"]}')
            print(f"gönderildi: {s['code']} {s['setup']} @ ₺{px:.2f}")
        except Exception as e:
            print(f"HATA {s['code']}: {e}")

    # yalnızca GERÇEKTEN gönderilenler + hâlâ geçerli eski gönderimler kaydedilir
    final = (sent & cur_keys) | delivered
    json.dump(sorted(final), open(p("signals_sent.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
