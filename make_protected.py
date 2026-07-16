#!/usr/bin/env python3
"""Build the password-protected dashboard page.

Reads:  users.json            [{"email": "...", "password": "..."}, ...]  (NEVER commit)
        ../bist100-dashboard/bist100_dashboard.html   (plaintext dashboard, NEVER commit)
        login_template.html
Writes: index.html            (login page + AES-256-GCM encrypted dashboard)

Crypto: one random 256-bit master key encrypts the dashboard (AES-GCM).
Per user, a key derived from their password (PBKDF2-HMAC-SHA256, 310k iters,
per-user salt) wraps the master key. E-mails are stored only as salted
SHA-256 fingerprints, so the public file leaks neither e-mails nor passwords.
"""
import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "..", "bist100-dashboard", "bist100_dashboard.html")
PBKDF2_ITERS = 310_000

b64 = lambda b: base64.b64encode(b).decode()

def main():
    users = json.load(open(os.path.join(HERE, "users.json")))
    if not users:
        sys.exit("users.json boş — en az bir kullanıcı gerekli")
    html = open(DASH, encoding="utf-8").read()

    master = os.urandom(32)
    p_iv = os.urandom(12)
    p_ct = AESGCM(master).encrypt(p_iv, html.encode(), None)

    email_salt = os.urandom(16)
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
        wrapped = AESGCM(kek).encrypt(w_iv, master, None)
        table[uid] = {"s": b64(salt), "i": b64(w_iv), "w": b64(wrapped)}

    tpl = open(os.path.join(HERE, "login_template.html"), encoding="utf-8").read()
    out = (tpl
           .replace("__USERS__", json.dumps(table))
           .replace("__EMAIL_SALT__", b64(email_salt))
           .replace("__P_IV__", b64(p_iv))
           .replace("__P_CT__", b64(p_ct)))
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    print(f"index.html yazıldı — {len(users)} kullanıcı, {len(out)//1024} KB")

if __name__ == "__main__":
    main()
