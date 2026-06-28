import { useState } from 'react'
import PortfolioPanel from './components/PortfolioPanel'
import FundExplorer from './components/FundExplorer'
import FundCompare from './components/FundCompare'
import Reminders from './components/Reminders'
import Alarms from './components/Alarms'

export default function App() {
  const [pickedCode, setPickedCode] = useState<string | undefined>(undefined)

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          UKCR <span className="badge">TEFAS Fon Takip</span>
        </h1>
        <p className="tagline">Sade &amp; etkin fon portföy takibi — XIRR, reel getiri, stopaj</p>
      </header>

      <main className="grid">
        <section className="col-main">
          <PortfolioPanel prefillCode={pickedCode} />
        </section>
        <aside className="col-side stack">
          <FundExplorer onPick={setPickedCode} />
          <Reminders />
          <Alarms />
        </aside>
      </main>

      <section className="compare-section">
        <FundCompare />
      </section>

      <footer className="app-footer">
        Veriler TEFAS'tan günlük NAV olarak alınır. Vergi bilgisi tahminîdir, yatırım/vergi tavsiyesi değildir.
      </footer>
    </div>
  )
}
