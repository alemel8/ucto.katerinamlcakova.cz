import type { InvoiceFilters } from '../types/invoice'

const MONTHS = [
  'Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
  'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec',
]

const currentYear = new Date().getFullYear()
const YEARS = Array.from({ length: 6 }, (_, i) => currentYear - i)

interface Props {
  filters: InvoiceFilters
  onChange: (f: InvoiceFilters) => void
  onReset: () => void
}

export default function InvoiceFilters({ filters, onChange, onReset }: Props) {
  function set<K extends keyof InvoiceFilters>(key: K, value: InvoiceFilters[K]) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-wrap gap-3 items-end">
      {/* Search */}
      <div className="flex-1 min-w-48">
        <label className="block text-xs font-medium text-gray-600 mb-1">Hledat</label>
        <input
          type="text"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
          placeholder="Firma, IČ, popis…"
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Year */}
      <div className="min-w-28">
        <label className="block text-xs font-medium text-gray-600 mb-1">Rok</label>
        <select
          value={filters.year}
          onChange={(e) => set('year', e.target.value ? Number(e.target.value) : '')}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Vše</option>
          {YEARS.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {/* Month */}
      <div className="min-w-36">
        <label className="block text-xs font-medium text-gray-600 mb-1">Měsíc</label>
        <select
          value={filters.month}
          onChange={(e) => set('month', e.target.value ? Number(e.target.value) : '')}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Vše</option>
          {MONTHS.map((m, i) => (
            <option key={i + 1} value={i + 1}>{m}</option>
          ))}
        </select>
      </div>

      {/* Date from */}
      <div className="min-w-36">
        <label className="block text-xs font-medium text-gray-600 mb-1">Od data</label>
        <input
          type="date"
          value={filters.date_from}
          onChange={(e) => set('date_from', e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Date to */}
      <div className="min-w-36">
        <label className="block text-xs font-medium text-gray-600 mb-1">Do data</label>
        <input
          type="date"
          value={filters.date_to}
          onChange={(e) => set('date_to', e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Reset */}
      <button
        onClick={onReset}
        className="px-4 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        Resetovat
      </button>
    </div>
  )
}
