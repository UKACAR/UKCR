# UKCR — TEFAS Fon Takip

Sade ve etkin, web tabanlı Türkiye yatırım fonu (TEFAS) takip uygulaması.
"Anti-FVT" yaklaşımıyla: reklamsız, hızlı ve fonları **doğru** takip etmeye odaklı —
şeffaf getiri matematiği, enflasyona göre reel getiri, tarihe-bağlı stopaj,
ve rakiplerde olmayan **vade/valör takibi**.

> ⚠️ Bu yazılım yatırım veya vergi tavsiyesi vermez. Vergi/stopaj hesapları
> tahminîdir. Veriler TEFAS'tan günlük NAV olarak alınır (anlık değildir).

## Özellikler

**Portföy & getiri**
- Çoklu portföy, hızlı alım/satım girişi (fiyat o günün NAV'ından otomatik)
- Lot bazlı **FIFO** maliyet, gerçekleşen/gerçekleşmemiş kâr-zarar
- **XIRR** (para-ağırlıklı getiri) + kümülatif getiri
- 🇹🇷 **Tarihe-bağlı stopaj** motoru (oran, lotun iktisap tarihine göre)
- Reel getiri için TCMB EVDS (TÜFE) altyapısı *(API anahtarı ile devreye girer)*

**Analiz**
- Fon arama + NAV grafiği
- **Fon karşılaştırma**: NAV'dan hesaplanan getiri/volatilite/maks. düşüş + ortak başlangıçtan rebased overlay grafik

**Takip & uyarı**
- **Vade/Valör takibi**: "bugün satarsan paran ne zaman elinde?" (iş-günü settlement) + hatırlatmalar
- **Fiyat alarmları**: NAV eşiği (üst/alt), canlı tetiklenme durumu

**Veri**
- TEFAS `api/funds` uçlarından ingestion + gecelik otomatik güncelleme (APScheduler)
- **CSV içe/dışa aktarma** (işlemler & pozisyonlar)

## Teknoloji

| Katman | Teknoloji |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy 2.0 · SQLite (dev) / Postgres (prod) |
| Veri/hesap | httpx · pandas · pyxirr · APScheduler |
| Frontend | React · Vite · TypeScript · TanStack Query · Recharts |

## Proje yapısı

```
fon-takip/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              # FastAPI app
│  │  ├─ core/config.py       # ayarlar (.env)
│  │  ├─ db/                  # models, session, init (+ stopaj takvimi)
│  │  ├─ ingestion/           # tefas.py (TEFAS adaptörü) + store.py
│  │  ├─ services/            # valuation · returns · tax · analytics · valor · evds · csvio
│  │  ├─ api/                 # funds · portfolios · compare · reminders · alarms
│  │  └─ scheduler.py         # gecelik güncelleme
│  └─ requirements.txt
└─ frontend/
   └─ src/                    # App · PortfolioPanel · FundExplorer · FundCompare · Reminders · Alarms · ImportExport
```

## Kurulum & çalıştırma

Gereksinimler: Python 3.12+, Node.js 18+ (LTS).

**Backend**
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload  # http://127.0.0.1:8000/docs
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Frontend `/api` isteklerini Vite proxy ile backend'e (8000) yönlendirir.

## Yapılandırma (`backend/.env`)

```env
# Üretimde Postgres:
DATABASE_URL=postgresql+psycopg://kullanici:sifre@host/db
# Reel getiri için TCMB EVDS (ücretsiz kayıt: evds2.tcmb.gov.tr):
EVDS_API_KEY=...
# Gecelik otomatik güncellemeyi uygulama içinde başlat:
ENABLE_SCHEDULER=true
```

## Veri yükleme

```bash
# Tüm TEFAS-açık fonları + 36 aylık NAV geçmişini doldur:
python -m app.ingestion.store all 36
# Tek fon:
python -m app.ingestion.store prices AAS 12
# Gecelik güncellemeyi tek seferlik çalıştır:
python -m app.scheduler once
```

## Notlar

- TEFAS uçları resmî olarak belgelenmemiştir; kullanım kişisel/araştırma amaçlıdır.
  Geniş ölçekli/yeniden dağıtımlı kullanım için Takasbank/MKK izni değerlendirilmelidir.
- Stopaj oranları zamanla değişir; `tax_rates` tablosu tarih-bazlı ve düzenlenebilirdir.
