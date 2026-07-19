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

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda n: os.path.join(HERE, n)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
# NUUK Quant grubu + "Sinyaller" topic'i (gizli değil; erişim yalnızca bot token'ıyla)
CHAT = os.environ.get("TELEGRAM_CHAT") or "-1002388620539"
THREAD = os.environ.get("TELEGRAM_THREAD") or "2299"


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

    # durum her zaman güncellenir (kaybolan sinyal tekrar gelirse yeniden uyarır)
    json.dump(sorted(cur_keys), open(p("signals_sent.json"), "w"), ensure_ascii=False)

    if not new:
        print("yeni RADAR sinyali yok, Telegram atlanıyor")
        return
    if not (TOKEN and CHAT):
        print(f"{len(new)} yeni sinyal var ama TELEGRAM_TOKEN/CHAT tanımlı değil — atlanıyor")
        return

    asof = sig.get("asOf", "")
    for s in new:
        msg = (
            f"📡 <b>NUUK BIST Radar</b> — yeni sinyal\n"
            f"🟢 <b>{s['code']}</b> · {s['setup']} · güç {s['strength']}/100\n\n"
            f"Yön: LONG\n"
            f"Giriş: ₺{tr(s['entry'])}\n"
            f"Stop: ₺{tr(s['stop'])} (−%{tr(s['riskPct'], 1)})\n"
            f"Hedefler: 1R ₺{tr(s['t1'])} · 2R ₺{tr(s['t2'])} · 3R ₺{tr(s['t3'])}\n"
            f"Temel skor: {s['fscore']}/100\n\n"
            + "".join(f"✓ {r}\n" for r in s.get("reasons", [])[:3])
            + f"\n<i>{asof}</i>\n"
            f"⚠️ Mekanik kurulum tespitidir; yatırım tavsiyesi değildir. Karar sizindir."
        )
        try:
            send(msg)
            print(f"gönderildi: {s['code']} {s['setup']}")
        except Exception as e:
            print(f"HATA {s['code']}: {e}")


if __name__ == "__main__":
    main()
