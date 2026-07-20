"""Build the encrypted, login-protected index.html (runs locally AND in CI).

Inputs:
  bist100_final.json    fresh data (from fetch_bist100.py + fix_data.py)
  radar_template.html   dashboard template (data injected at /*__DATA__*/null)
  login_template.html   login shell (placeholders __USERS__ etc.)
  keys.json             public-safe user table: salted e-mail hashes + wrapped master key
  env MASTER_KEY        base64 32-byte AES key (GitHub Actions secret / local .master.secret)

Output: index.html — login page + AES-256-GCM encrypted dashboard, stamped with build time.
"""
import base64
import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda name: os.path.join(HERE, name)

master_b64 = os.environ.get("MASTER_KEY")
if not master_b64 and os.path.exists(p(".master.secret")):
    master_b64 = open(p(".master.secret")).read().strip()
if not master_b64:
    sys.exit("MASTER_KEY ortam değişkeni yok (veya yerelde .master.secret dosyası)")
master = base64.b64decode(master_b64)
if len(master) != 32:
    sys.exit("MASTER_KEY 32 bayt olmalı")

keys = json.load(open(p("keys.json")))
data = json.load(open(p("bist100_final.json")))

# teknik katman (fetch_technical.py çıktısı) — yoksa pano temel verilerle çalışmaya devam eder
if os.path.exists(p("technical.json")):
    tech = json.load(open(p("technical.json")))
    data["tech"] = tech.get("stocks", {})
    data["market"] = tech.get("market", {})

# sinyal motoru + takip çıktısı (compute_signals.py -> track_signals.py)
if os.path.exists(p("signals.json")):
    sg = json.load(open(p("signals.json")))
    data["signals"] = sg.get("signals", [])
    data["signalCounts"] = sg.get("counts", {})
    data["marketOpen"] = sg.get("marketOpen", True)

TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
now = datetime.datetime.now(ZoneInfo("Europe/Istanbul"))
data["asOf"] = f"{now.day} {TR_MONTHS[now.month]} {now.year}, {now:%H:%M} (saatlik otomatik güncelleme)"

dashboard = (open(p("radar_template.html"), encoding="utf-8").read()
             .replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)))

iv = os.urandom(12)
ct = AESGCM(master).encrypt(iv, dashboard.encode(), None)
b64 = lambda b: base64.b64encode(b).decode()

# Giriş modeli: supabase.json (url+anon, herkese açık) varsa Supabase Auth (kendi
# kayıt), yoksa eski kişi-başı şifre şablonu. Geçiş kesintisiz.
if os.path.exists(p("supabase.json")):
    cfg = json.load(open(p("supabase.json")))
    out = (open(p("login_supabase_template.html"), encoding="utf-8").read()
           .replace("__SUPABASE_URL__", cfg["url"])
           .replace("__SUPABASE_ANON__", cfg["anon"])
           .replace("__P_IV__", b64(iv))
           .replace("__P_CT__", b64(ct)))
else:
    out = (open(p("login_template.html"), encoding="utf-8").read()
           .replace("__USERS__", json.dumps(keys["users"]))
           .replace("__EMAIL_SALT__", keys["emailSalt"])
           .replace("__P_IV__", b64(iv))
           .replace("__P_CT__", b64(ct)))

with open(p("index.html"), "w", encoding="utf-8") as f:
    f.write(out)
print(f"index.html yazıldı — {len(keys['users'])} kullanıcı, {len(out)//1024} KB, damga: {data['asOf']}")
