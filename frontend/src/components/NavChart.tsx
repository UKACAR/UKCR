import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PricePoint } from '../types'

export default function NavChart({ data }: { data: PricePoint[] }) {
  if (!data.length) return <p className="muted">Fiyat verisi yok.</p>

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          minTickGap={28}
          fontSize={11}
          stroke="var(--muted)"
        />
        <YAxis
          domain={['auto', 'auto']}
          width={56}
          fontSize={11}
          stroke="var(--muted)"
          tickFormatter={(v: number) => v.toFixed(3)}
        />
        <Tooltip
          formatter={(value) => [Number(value).toFixed(6), 'NAV']}
          labelFormatter={(label) => String(label)}
        />
        <Line type="monotone" dataKey="price" stroke="var(--accent)" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  )
}
