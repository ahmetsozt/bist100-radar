# NUUK BIST Radar

BIST 100 hisseleri için temel analiz panosu. İçerik **AES-256-GCM ile şifrelidir**;
yalnızca davet edilen e-posta + şifre çiftleri panoyu tarayıcıda çözebilir.

## Saatlik otomatik güncelleme

GitHub Actions (`.github/workflows/update.yml`) her saat başı çalışır:

```
fetch_bist100.py   →  100 hissenin fiyat + çeyreklik finansallarını çeker (yfinance)
fetch_technical.py →  2 yıllık günlük OHLCV'den teknik göstergeleri hesaplar
                      (SMA/RSI/MACD/ATR/relatif güç + XU100 rejimi)
fix_data.py        →  USD/EUR raporlayanları güncel kurla TL'ye çevirir,
                      büyümeleri tarih eşleştirmeli hesaplar
compute_signals.py →  SİNYAL MOTORU: kurulum tespiti (Kırılım/Geri çekilme/Momentum/
                      Trend devamı/Dönüş) → ATR planı → risk kapısı → RADAR/İZLE/GEÇ
build_site.py      →  veriyi + sinyalleri şablona gömer, MASTER_KEY ile şifreler,
                      saat damgalı index.html üretir
telegram_push.py   →  yalnızca YENİ RADAR sinyallerini Telegram'a iletir (state:
                      signals_sent.json ile dedup, saatlik spam olmaz)
```

## Sinyal motoru (Fable 5 döngüsü uyarlaması)

Boru hattı: **Tara → Sinyal → Plan → Risk → Karar → İlet**. Kurulum tanımları ve
karar eşikleri panonun Metodoloji sekmesinde ve `compute_signals.py` içinde yazılıdır.
Tümü mekanik kural çıktısıdır, geriye dönük test edilmemiştir, **yatırım tavsiyesi
değildir** — sistem kurulumu bulur, kararı insan verir.

Telegram iletimi için iki GitHub Actions secret gerekir (yoksa adım sessizce atlanır):
`TELEGRAM_TOKEN` (bot token) ve `TELEGRAM_CHAT` (hedef chat/kanal id).

Veri çekimi başarısız olursa (ör. kaynak erişilemezse) site **son başarılı
veriyle** kalır; bir sonraki saat yeniden denenir. Başlıktaki saat damgası her
zaman verinin gerçek yaşını gösterir.

## Anahtar mimarisi

- Pano tek bir 256-bit **ana anahtarla** şifrelenir. Bu anahtar GitHub'da
  yalnızca Actions secret'ı (`MASTER_KEY`) olarak durur.
- Her kullanıcının şifresinden PBKDF2 (310k tur) ile türetilen anahtar, ana
  anahtarı sarmalar → `keys.json` (herkese açık ama işe yaramaz: e-postalar
  tuzlu SHA-256 parmak izi, şifreler hiçbir yerde yok).
- **Yatırımcı şifreleri asla GitHub'a gitmez** — `users.json` yalnızca yerel
  makinede durur ve `.gitignore`'dadır.

## Yatırımcı ekleme

Yerel makinede:

```bash
# 1. users.json'a satır ekle:  {"email": "...", "password": "..."}
python3 make_keys.py          # keys.json'ı günceller
git add keys.json && git commit -m "chore: erişim listesi" && git push
```

Bir sonraki saatlik derlemede (veya Actions'ta workflow'u elle çalıştırınca)
yeni kullanıcı giriş yapabilir.

## Yatırımcı çıkarma

```bash
# 1. users.json'dan satırı sil
python3 make_keys.py --rotate  # YENİ ana anahtar üretir
# 2. GitHub → Settings → Secrets → Actions → MASTER_KEY değerini
#    yeni .master.secret içeriğiyle değiştir
git add keys.json && git commit -m "chore: erişim iptali" && git push
```

Rotasyon olmadan silme yeterli değildir: eski kullanıcı ana anahtarı
tarayıcısında saklamış olabilir.

## BIST 100 bileşimi

Hisse listesi `fetch_bist100.py` içinde sabittir; BIST endeks bileşimi
çeyrekte bir değiştiği için listeyi ara sıra güncellemek gerekir.

*Bu pano bilgilendirme amaçlıdır; yatırım tavsiyesi değildir.*
