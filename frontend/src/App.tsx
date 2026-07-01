import { useEffect, useState } from 'react'
import type { ComponentType } from 'react'
import PortfolioPanel from './components/PortfolioPanel'
import FundExplorer from './components/FundExplorer'
import FundCompare from './components/FundCompare'
import Favorites from './components/Favorites'
import Metals from './components/Metals'
import MarketBoard from './components/MarketBoard'
import EtfMarket from './components/EtfMarket'
import Reminders from './components/Reminders'
import Alarms from './components/Alarms'
import Overview from './components/Overview'
import AiAnalysis from './components/AiAnalysis'

type ViewId =
  | 'overview'
  | 'ai'
  | 'favorites'
  | 'portfolio'
  | 'explore'
  | 'compare'
  | 'metals'
  | 'bist'
  | 'crypto'
  | 'etf'
  | 'viop'
  | 'world'
  | 'reminders'
  | 'alarms'

const NAV: { id: ViewId; label: string; Icon: ComponentType }[] = [
  { id: 'overview', label: 'Günün Özeti', Icon: IconHome },
  { id: 'favorites', label: 'Favorilerim', Icon: IconStar },
  { id: 'portfolio', label: 'Portföyüm', Icon: IconPortfolio },
  { id: 'explore', label: 'Fon Keşfi', Icon: IconSearch },
  { id: 'compare', label: 'Fon Karşılaştırma', Icon: IconCompare },
  { id: 'bist', label: 'BİST İstanbul', Icon: IconBist },
  { id: 'metals', label: 'Kıymetli Madenler & Emtia', Icon: IconMetal },
  { id: 'crypto', label: 'Kripto', Icon: IconCrypto },
  { id: 'etf', label: 'ETF', Icon: IconEtf },
  { id: 'viop', label: 'VİOP', Icon: IconViop },
  { id: 'world', label: 'Dünya Borsaları', Icon: IconWorld },
  { id: 'reminders', label: 'Vade & Hatırlatma', Icon: IconBell },
  { id: 'alarms', label: 'Fiyat Alarmı', Icon: IconAlarm },
  { id: 'ai', label: 'AI Analiz', Icon: IconAi },
]

export default function App() {
  const [view, setView] = useState<ViewId>('overview')
  const [collapsed, setCollapsed] = useState(false)
  const [pickedCode, setPickedCode] = useState<string | undefined>(undefined)
  const [openTarget, setOpenTarget] = useState<{ code: string; n: number } | undefined>(undefined)

  // Başka ekrandan bir fona tıklanınca Fon Keşfi'nde o fonun detayını aç.
  const openFund = (code: string) => {
    setOpenTarget((p) => ({ code, n: (p?.n ?? 0) + 1 }))
    setView('explore')
  }

  const current = NAV.find((n) => n.id === view) ?? NAV[0]

  return (
    <div className={`layout ${collapsed ? 'collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="sidebar-head">
          <span className="brand">UKCR</span>
          <button
            className="collapse-btn"
            title={collapsed ? 'Menüyü genişlet' : 'Menüyü daralt'}
            onClick={() => setCollapsed((c) => !c)}
          >
            {collapsed ? '»' : '«'}
          </button>
        </div>

        <div className="menu-label">ANA MENÜ</div>
        <nav className="nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? 'active' : ''}`}
              onClick={() => {
                setOpenTarget(undefined) // menüden gelince Fon Keşfi temiz açılsın
                setView(item.id)
              }}
              title={item.label}
            >
              <span className="nav-icon">
                <item.Icon />
              </span>
              <span className="nav-text">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">TEFAS Fon Takip</div>
      </aside>

      <div className="content">
        <header className="app-header">
          <div>
            <h1>{current.label}</h1>
            <p className="tagline">Sade &amp; etkin fon portföy takibi — XIRR, reel getiri, stopaj</p>
          </div>
          <Clock />
        </header>

        <main className="view">
          {view === 'overview' && (
            <Overview onGoPortfolio={() => setView('portfolio')} onOpenFund={openFund} />
          )}
          {view === 'ai' && <AiAnalysis />}
          {view === 'favorites' && <Favorites onOpenFund={openFund} />}
          {view === 'portfolio' && <PortfolioPanel prefillCode={pickedCode} />}
          {view === 'explore' && (
            <FundExplorer
              openTarget={openTarget}
              onPick={(c) => {
                setPickedCode(c)
                setView('portfolio')
              }}
            />
          )}
          {view === 'compare' && <FundCompare onOpenFund={openFund} />}
          {view === 'metals' && <Metals />}
          {view === 'bist' && (
            <MarketBoard
              board="bist"
              moversBoard="bist"
              newsTopic="bist"
              newsTitle="BİST & Piyasa Haberleri"
              note="Endeks/hisse değerleri ~15 dk gecikmeli (Yahoo Finance)."
            />
          )}
          {view === 'crypto' && (
            <MarketBoard
              board="crypto"
              moversBoard="crypto"
              usdPrimary
              newsTopic="crypto"
              newsTitle="Kripto Haberleri"
              note="Fiyatlar USD; yanında TL karşılığı (güncel kur ile) · ~15 dk gecikmeli."
            />
          )}
          {view === 'etf' && <EtfMarket onOpenFund={openFund} />}
          {view === 'viop' && (
            <MarketBoard
              board="viop"
              newsTopic="viop"
              newsTitle="VİOP & Vadeli Haberler"
              note="VİOP sözleşme verisi ücretsiz olmadığından dayanak varlıklar (BİST 30, döviz, altın, gümüş) gösterilir."
            />
          )}
          {view === 'world' && (
            <MarketBoard
              board="world"
              showStats
              newsTopic="world"
              newsTitle="Dünya Piyasa Haberleri"
              note="Küresel endeksler ~15 dk gecikmeli; farklı saat dilimleri nedeniyle bazıları kapalı olabilir."
            />
          )}
          {view === 'reminders' && <Reminders />}
          {view === 'alarms' && <Alarms />}
        </main>

        <footer className="app-footer">
          Veriler TEFAS'tan günlük NAV olarak alınır. Vergi bilgisi tahminîdir, yatırım/vergi tavsiyesi değildir.
        </footer>
      </div>
    </div>
  )
}

const DAYS = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi']
const MONTHS = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
]

function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="clock">
      <div className="clock-date">
        {DAYS[now.getDay()]}, {now.getDate()} {MONTHS[now.getMonth()]}
      </div>
      <div className="clock-time">{now.toLocaleTimeString('tr-TR')}</div>
    </div>
  )
}

/* --- Basit çizgi ikonlar (currentColor) --- */
const svg = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

function IconAi() {
  return (
    <svg {...svg}>
      <rect x="4" y="7" width="16" height="12" rx="2.5" />
      <path d="M12 7V4M9 4h6" />
      <circle cx="9" cy="13" r="1" />
      <circle cx="15" cy="13" r="1" />
      <path d="M2 12v2M22 12v2" />
    </svg>
  )
}

function IconHome() {
  return (
    <svg {...svg}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

function IconStar() {
  return (
    <svg {...svg}>
      <path d="M12 3.5l2.6 5.3 5.9.85-4.25 4.15 1 5.85L12 17.1l-5.25 2.6 1-5.85L3.5 9.65l5.9-.85L12 3.5z" />
    </svg>
  )
}

function IconMetal() {
  return (
    <svg {...svg}>
      <path d="M6 3h12l3 6-9 12L3 9z" />
      <path d="M3 9h18" />
      <path d="M9 3l3 6 3-6" />
    </svg>
  )
}

function IconBist() {
  return (
    <svg {...svg}>
      <path d="M12 3l9 5H3z" />
      <path d="M4 8v10M9 8v10M15 8v10M20 8v10" />
      <path d="M3 21h18" />
    </svg>
  )
}

function IconCrypto() {
  return (
    <svg {...svg}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 8h4a2 2 0 0 1 0 4h-4zM9.5 12h4.3a2 2 0 0 1 0 4H9.5zM9.5 8v8" />
      <path d="M11 6.5v1.5M13 6.5v1.5M11 16v1.5M13 16v1.5" />
    </svg>
  )
}

function IconEtf() {
  return (
    <svg {...svg}>
      <path d="M12 3l9 5-9 5-9-5z" />
      <path d="M3 12l9 5 9-5" />
      <path d="M3 16.5l9 5 9-5" />
    </svg>
  )
}

function IconViop() {
  return (
    <svg {...svg}>
      <path d="M4 8h13l-3-3" />
      <path d="M20 16H7l3 3" />
    </svg>
  )
}

function IconWorld() {
  return (
    <svg {...svg}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18" />
    </svg>
  )
}

function IconPortfolio() {
  return (
    <svg {...svg}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M3 12h18" />
    </svg>
  )
}

function IconSearch() {
  return (
    <svg {...svg}>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  )
}

function IconCompare() {
  return (
    <svg {...svg}>
      <path d="M3 20h18" />
      <rect x="5" y="11" width="3" height="6" rx="1" />
      <rect x="11" y="6" width="3" height="11" rx="1" />
      <rect x="17" y="9" width="3" height="8" rx="1" />
    </svg>
  )
}

function IconBell() {
  return (
    <svg {...svg}>
      <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 8 2.5 8h-17S6 15 6 9" />
      <path d="M10.5 21a2 2 0 0 0 3 0" />
    </svg>
  )
}

function IconAlarm() {
  return (
    <svg {...svg}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 2" />
      <path d="M5 3 2.5 5.5" />
      <path d="M19 3l2.5 2.5" />
    </svg>
  )
}
