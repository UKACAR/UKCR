import { useEffect, useState } from 'react'
import type { ComponentType } from 'react'
import PortfolioPanel from './components/PortfolioPanel'
import FundExplorer from './components/FundExplorer'
import FundCompare from './components/FundCompare'
import Reminders from './components/Reminders'
import Alarms from './components/Alarms'
import Overview from './components/Overview'

type ViewId = 'overview' | 'portfolio' | 'explore' | 'compare' | 'reminders' | 'alarms'

const NAV: { id: ViewId; label: string; Icon: ComponentType }[] = [
  { id: 'overview', label: 'Günün Özeti', Icon: IconHome },
  { id: 'portfolio', label: 'Portföyüm', Icon: IconPortfolio },
  { id: 'explore', label: 'Fon Keşfi', Icon: IconSearch },
  { id: 'compare', label: 'Fon Karşılaştırma', Icon: IconCompare },
  { id: 'reminders', label: 'Vade & Hatırlatma', Icon: IconBell },
  { id: 'alarms', label: 'Fiyat Alarmı', Icon: IconAlarm },
]

export default function App() {
  const [view, setView] = useState<ViewId>('overview')
  const [collapsed, setCollapsed] = useState(false)
  const [pickedCode, setPickedCode] = useState<string | undefined>(undefined)

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
              onClick={() => setView(item.id)}
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
          {view === 'overview' && <Overview onGoPortfolio={() => setView('portfolio')} />}
          {view === 'portfolio' && <PortfolioPanel prefillCode={pickedCode} />}
          {view === 'explore' && (
            <FundExplorer
              onPick={(c) => {
                setPickedCode(c)
                setView('portfolio')
              }}
            />
          )}
          {view === 'compare' && <FundCompare />}
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
