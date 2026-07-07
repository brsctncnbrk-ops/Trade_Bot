# Binance Spot Trading Bot — Test ve Backtest Sistemi

Güvenli, modüler ve test edilebilir bir Binance Spot alım-satım botu.

> ⚠️ **ÖNEMLİ: Bu ilk sürümde CANLI İŞLEM YOKTUR.**
> Bot varsayılan olarak `backtest` modunda çalışır, hiçbir gerçek emir
> göndermez ve Binance API anahtarı gerektirmez. Canlı emir gönderim yolu
> kod seviyesinde devre dışıdır.

## 1. Projenin Amacı

Bu projenin ilk hedefi kâr etmek değildir. İlk hedef:

- **Güvenli mimari** — canlı işlem kazara açılamaz.
- **Test edilebilir kod** — her modül pytest ile test edilir.
- **Backtest desteği** — strateji geçmiş/örnek veri üzerinde simüle edilir.
- **GitHub Actions otomasyonu** — her push'ta testler, istenirse backtest çalışır.

Mimari modülerdir: veri sağlayıcı, göstergeler, strateji, risk yöneticisi,
emir yürütme, durum takibi ve loglama ayrı modüllerdir. Böylece ileride
Lumibot gibi bir framework'e geçiş veya VPS dağıtımı kolay olur.

## 2. Güvenlik Kuralları

- Varsayılan mod **backtest**'tir; API anahtarı gerektirmez.
- `MODE=live` tek başına **çalışmaz**. Ek olarak `ALLOW_LIVE_TRADING=true`
  verilmezse yapılandırma yüklenirken hata alırsınız.
- Bu sürümde `ALLOW_LIVE_TRADING=true` verilse bile gerçek emir yolu
  kapalıdır (`NotImplementedError`).
- Hiçbir emir, **risk yöneticisi onayı** olmadan verilemez.
- Hiçbir alış emri, **stop-loss ve take-profit** olmadan verilemez.
- Sembol başına en fazla **bir açık pozisyon** olabilir.
- **Günlük zarar limiti** aşılırsa bot yeni işlem açmaz.
- **Günlük işlem limiti** dolunca bot yeni işlem açmaz.
- Loglarda API sırları asla görünmez (maskelenir).

## 3. Kurulum Adımları

### 3.1. Depoyu klonlayın

```bash
git clone https://github.com/brsctncnbrk-ops/Trade_Bot.git
cd Trade_Bot
```

### 3.2. Sanal ortam oluşturun

```bash
python -m venv .venv
```

Sanal ortamı etkinleştirin:

**Windows:**

```bash
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
source .venv/bin/activate
```

### 3.3. Paketleri kurun

```bash
pip install -r requirements.txt
```

### 3.4. Ortam dosyasını hazırlayın

`.env.example` dosyasını `.env` olarak kopyalayın:

**Windows:**

```bash
copy .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Backtest için `.env` dosyasına dokunmanıza gerek yoktur — varsayılan
değerlerle çalışır. Testnet denemek isterseniz
[testnet.binance.vision](https://testnet.binance.vision) üzerinden aldığınız
anahtarları `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET`
alanlarına yazın.

## 4. Testleri Çalıştırma

```bash
pytest
```

Tüm testler çevrimdışı çalışır; internet bağlantısı ve API anahtarı
gerektirmez. Ayrıntılı çıktı için:

```bash
pytest -v
```

## 5. Backtest Çalıştırma

```bash
python backtests/run_backtest.py
```

- `data/sample/` altında örnek CSV verisi varsa onu kullanır.
- Yoksa **deterministik** (her çalıştırmada aynı) sahte OHLCV verisi üretir,
  yani API anahtarı olmadan da çalışır.
- Rapor hem ekrana basılır hem `backtest_report.txt` dosyasına yazılır.

Rapor şunları içerir: başlangıç/son bakiye, net kâr-zarar, toplam işlem,
kazanma oranı, maksimum düşüş (drawdown), profit factor, ortalama işlem
getirisi, en büyük kazanç ve en büyük zarar.

Gerçek geçmiş veriyle backtest yapmak isterseniz (API anahtarı gerekmez,
halka açık uç kullanılır):

```bash
python scripts/download_sample_data.py
python backtests/run_backtest.py
```

Yapılandırmanızı kontrol etmek için:

```bash
python scripts/check_config.py
```

## 6. GitHub Actions Kullanım Mantığı

İki workflow vardır ve **hiçbiri Binance API secret'ı gerektirmez**:

| Workflow | Tetikleyici | Ne yapar |
|---|---|---|
| `.github/workflows/tests.yml` | Her push ve pull request | Python 3.11 kurar, bağımlılıkları yükler, `pytest` çalıştırır |
| `.github/workflows/backtest.yml` | `main`'e push + manuel (workflow_dispatch) | Backtest'i çalıştırır, raporu ekrana basar ve artifact olarak yükler |

Manuel backtest için: GitHub → **Actions** sekmesi → **Backtest** →
**Run workflow**. Çalışma bitince raporu hem log çıktısında hem de
"Artifacts" bölümünde `backtest-report` olarak bulabilirsiniz.

## 7. Binance API Anahtarı Güvenlik Uyarıları

- API anahtarlarınızı **asla** koda yazmayın, **asla** commit etmeyin.
  `.env` dosyası `.gitignore` içindedir — öyle kalmalıdır.
- Binance'te API anahtarı oluştururken **withdrawal (para çekme) iznini
  ASLA vermeyin**. Bu bot para çekme izni gerektirmez ve hiçbir zaman
  gerektirmeyecektir.
- Mümkünse API anahtarını IP kısıtlamasıyla sınırlayın.
- Önce **testnet** anahtarlarıyla deneyin; gerçek anahtarları yalnızca
  sistemin tamamına güvendiğinizde ve küçük tutarlarla kullanın.
- GitHub Actions'ta gerçek anahtar kullanmayın. İleride testnet
  entegrasyon testleri gerekirse anahtarlar yalnızca **GitHub Secrets**
  üzerinden ve ayrı bir workflow'da kullanılmalıdır.
- Bir anahtarın sızdığından şüphelenirseniz Binance panelinden hemen
  silin ve yenisini oluşturun.

## 8. Proje Yapısı

```
├─ config/          # pydantic tabanlı yapılandırma ve doğrulama
├─ bot/
│  ├─ data_provider.py   # veri: örnek CSV / deterministik üretim / CCXT
│  ├─ indicators.py      # EMA 20/50, RSI 14
│  ├─ strategy.py        # sinyal üretimi (asla emir vermez)
│  ├─ risk_manager.py    # her işlemin onay makamı
│  ├─ execution.py       # emir simülasyonu / testnet / (kapalı) live
│  ├─ state.py           # pozisyonlar, günlük PnL ve işlem sayacı
│  ├─ logger.py          # loguru kurulumu, sır maskeleme
│  └─ alerts.py          # opsiyonel Telegram bildirimleri
├─ backtests/       # backtest çalıştırıcısı ve metrik raporu
├─ live/            # tek döngü çalıştırıcı (gelecekteki VPS giriş noktası)
├─ scripts/         # yapılandırma kontrolü, örnek veri indirme
├─ tests/           # pytest test paketi (tamamen çevrimdışı)
└─ .github/workflows/  # CI: testler ve backtest
```

## 9. Strateji (İlk Sürüm)

EMA 20 / EMA 50 kesişimi + RSI 14 filtresi:

- **Alış:** EMA20 > EMA50 **ve** RSI < 70 **ve** açık pozisyon yok.
- **Satış:** stop-loss veya take-profit seviyesi görülür **veya** EMA20 < EMA50.
- Stop-loss: giriş fiyatının %2 altı. Take-profit: %4 üstü (`.env`'den ayarlanır).
- Pozisyon büyüklüğü: `bakiye × işlem başına risk / stop mesafesi`
  (bakiyeyi aşamaz).

## 10. Gelecek Plan: VPS'ye Taşıma

Bu sürümde VPS dağıtımı **yoktur**; mimari buna hazırdır. Yol haritası:

1. **Testnet aşaması:** `MODE=testnet` ile `live/run_once.py` kullanılarak
   Binance Spot Testnet üzerinde uçtan uca emir akışının doğrulanması.
2. **Kalıcı durum:** pozisyon ve günlük sayaçların dosya/SQLite ile
   kalıcı hale getirilmesi.
3. **Zamanlama:** VPS üzerinde cron veya systemd timer ile
   `live/run_once.py`'nin periyodik çalıştırılması.
4. **İzleme:** Telegram bildirimlerinin zorunlu hale getirilmesi,
   log rotasyonu ve sağlık kontrolleri.
5. **Canlı geçiş (en son):** küçük tutarlarla, `MODE=live` +
   `ALLOW_LIVE_TRADING=true` çifte onayı ve gerçek emir yolunun bilinçli
   olarak açılmasıyla.

İsterseniz ileride Lumibot entegrasyonu da bu modüler yapı üzerine
eklenebilir; strateji ve risk kuralları framework'ten bağımsız yazılmıştır.

## Hızlı Komut Özeti

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
pytest
python backtests/run_backtest.py
```
