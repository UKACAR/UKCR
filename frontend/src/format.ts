const trCurrency = new Intl.NumberFormat('tr-TR', {
  style: 'currency',
  currency: 'TRY',
  maximumFractionDigits: 2,
})

const trPercent = new Intl.NumberFormat('tr-TR', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** TL biçimi (Türk Lirası). */
export const tl = (v: number | null | undefined): string =>
  v == null ? '—' : trCurrency.format(v)

/** Ondalık oranı yüzdeye çevirir (0.69 -> %69,00). */
export const pct = (v: number | null | undefined): string =>
  v == null ? '—' : trPercent.format(v)

/** Genel sayı biçimi. */
export const num = (v: number | null | undefined, frac = 6): string =>
  v == null
    ? '—'
    : new Intl.NumberFormat('tr-TR', { maximumFractionDigits: frac }).format(v)

/** Zaten yüzde olan değerler için (TEFAS dönem getirileri: -9.79 -> %-9,79). */
export const pctRaw = (v: number | null | undefined): string =>
  v == null ? '—' : `%${num(v, 2)}`
