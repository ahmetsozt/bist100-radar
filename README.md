# BIST 100 Finansal Radar

BIST 100 hisseleri için temel analiz panosu. İçerik **AES-256-GCM ile şifrelidir**;
yalnızca davet edilen e-posta + şifre çiftleri panoyu tarayıcıda çözebilir.

## Nasıl çalışır

- `index.html` = giriş sayfası + şifreli pano (tek statik dosya, GitHub Pages'te barınır).
- Pano tek bir rastgele ana anahtarla şifrelenir; her kullanıcının şifresinden
  PBKDF2 (310k tur) ile türetilen anahtar, ana anahtarı sarmalar.
- E-postalar dosyada yalnızca tuzlu SHA-256 parmak izi olarak durur —
  yayınlanan dosyadan e-posta veya şifre çıkarılamaz.

## Yatırımcı ekleme / çıkarma

1. `users.json` düzenle (bu dosya **asla** commit edilmez):
   ```json
   [
     {"email": "yatirimci@ornek.com", "password": "guclu-bir-sifre"}
   ]
   ```
2. Yeniden derle ve yayınla:
   ```bash
   python3 make_protected.py
   git add index.html && git commit -m "chore: erişim listesi güncellendi" && git push
   ```

Not: Şifresi olan herkes içeriğin tamamını çözebilir; kullanıcı çıkarmak
ancak yeniden derleyip yayınlamakla etkili olur (yeni ana anahtar üretilir).

## Veri güncelleme

Pano verisi `../bist100-dashboard/` pipeline'ı ile üretilir
(`fetch_bist100.py` → `fix_data.py` → şablona gömme), sonra burada
`python3 make_protected.py` çalıştırılır.

*Bu pano bilgilendirme amaçlıdır; yatırım tavsiyesi değildir.*
