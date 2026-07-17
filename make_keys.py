"""LOCAL-ONLY tool: (re)generate keys.json from users.json.

users.json      [{"email": "...", "password": "..."}]  — NEVER committed
.master.secret  base64 master key                      — NEVER committed
keys.json       public-safe output (committed): salted e-mail fingerprints
                + master key wrapped per user via PBKDF2(310k)+AES-GCM

Investor passwords never leave this machine; CI only needs MASTER_KEY.
Run with --rotate after REMOVING an investor (new master key; remember to
update the MASTER_KEY secret on GitHub afterwards).
"""
import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
p = lambda name: os.path.join(HERE, name)
PBKDF2_ITERS = 310_000
b64 = lambda b: base64.b64encode(b).decode()

rotate = "--rotate" in sys.argv
if rotate or not os.path.exists(p(".master.secret")):
    master = os.urandom(32)
    open(p(".master.secret"), "w").write(b64(master))
    os.chmod(p(".master.secret"), 0o600)
    print("YENİ master anahtar üretildi → GitHub'daki MASTER_KEY secret'ını da güncelle!")
else:
    master = base64.b64decode(open(p(".master.secret")).read().strip())

old = {}
if os.path.exists(p("keys.json")) and not rotate:
    old = json.load(open(p("keys.json")))
email_salt = base64.b64decode(old["emailSalt"]) if old.get("emailSalt") else os.urandom(16)

users = json.load(open(p("users.json")))
table = {}
for u in users:
    email = u["email"].strip().lower()
    pw = u["password"].strip()
    if len(pw) < 8:
        sys.exit(f"{email}: şifre en az 8 karakter olmalı")
    uid = hashlib.sha256(email_salt + email.encode()).hexdigest()[:24]
    salt = os.urandom(16)
    kek = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ITERS, dklen=32)
    w_iv = os.urandom(12)
    table[uid] = {"s": b64(salt), "i": b64(w_iv), "w": b64(AESGCM(kek).encrypt(w_iv, master, None))}

json.dump({"emailSalt": b64(email_salt), "users": table}, open(p("keys.json"), "w"), indent=1)
print(f"keys.json yazıldı — {len(users)} kullanıcı")
