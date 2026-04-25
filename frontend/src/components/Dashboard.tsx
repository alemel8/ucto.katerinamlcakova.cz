import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { fetchInvoices, syncEmails, getPohodaExportUrl, updateInvoice, getPdfUrl, fetchClients } from '../api/invoices'
import type { Invoice, InvoiceFilters, Client } from '../types/invoice'
import InvoiceFiltersBar from './InvoiceFilters'
import InvoiceTable from './InvoiceTable'

const DEFAULT_FILTERS: InvoiceFilters = {
  search: '',
  year: '',
  month: '',
  date_from: '',
  date_to: '',
  client_ico: '',
}

export default function Dashboard() {
  const { logout, token } = useAuth()
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [clients, setClients] = useState<Client[]>([])
  const [updateError, setUpdateError] = useState('')
  const [pdfInvoice, setPdfInvoice] = useState<Invoice | null>(null)
  const [filters, setFilters] = useState<InvoiceFilters>(DEFAULT_FILTERS)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')
  const [error, setError] = useState('')
  const [liveMsg, setLiveMsg] = useState('')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    fetchClients().then(setClients).catch(() => {})
  }, [])

  const loadInvoices = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchInvoices(filters)
      setInvoices(data)
    } catch (e: unknown) {
      setError('Chyba při načítání faktur')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    loadInvoices()
  }, [loadInvoices])

  // ── WebSocket: auto-refresh when backend notifies new invoice ──────────────
  useEffect(() => {
    if (!token) return

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
    let ws: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')
      }

      ws.onmessage = (evt) => {
        if (evt.data === 'new_invoice') {
          setLiveMsg('Nová faktura přijata — aktualizuji...')
          loadInvoices().then(() => {
            setLiveMsg('✓ Tabulka aktualizována')
            setTimeout(() => setLiveMsg(''), 4000)
          })
        }
      }

      ws.onclose = () => {
        // Reconnect after 5s
        reconnectTimer = setTimeout(connect, 5000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [token, loadInvoices])

  async function handleSync(all: boolean) {
    setSyncing(true)
    setSyncMsg('')
    setError('')
    try {
      const res = await syncEmails(all)
      setSyncMsg(res.message)
      await loadInvoices()
    } catch (e: unknown) {
      setError('Chyba při synchronizaci e-mailů')
      console.error(e)
    } finally {
      setSyncing(false)
    }
  }

  function handlePohodaExport(ids: number[]) {
    const url = getPohodaExportUrl(ids)
    window.open(url, '_blank')
  }

  // Escape closes PDF panel; ArrowUp/Down navigates between rows with attachments
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPdfInvoice(null); return }
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
      // Always prevent default for arrow keys (stops page scroll and link activation)
      e.preventDefault()
      if (!pdfInvoice) return
      // Skip navigation when user is typing in an input
      const tag = (document.activeElement as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      // Use DOM order so navigation matches the visual table order exactly
      const domIds = Array.from(
        document.querySelectorAll<HTMLElement>('tr[data-invoice-id]')
      ).map(el => parseInt(el.dataset.invoiceId!, 10))
      const withPdf = domIds
        .map(id => invoices.find(i => i.id === id))
        .filter((i): i is Invoice => !!i && !!i.pdf_filename)
      const idx = withPdf.findIndex(i => i.id === pdfInvoice.id)
      if (idx === -1) return
      const nextIdx = e.key === 'ArrowDown' ? idx + 1 : idx - 1
      if (nextIdx >= 0 && nextIdx < withPdf.length) setPdfInvoice(withPdf[nextIdx])
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [pdfInvoice, invoices])

  const handleUpdate = useCallback(async (id: number, patch: Record<string, unknown>) => {
    try {
      const updated = await updateInvoice(id, patch as Partial<Invoice>)
      setInvoices(prev => prev.map(inv => inv.id === id ? updated : inv))
    } catch (e: unknown) {
      setUpdateError('Chyba při ukládání úpravy')
      console.error(e)
      setTimeout(() => setUpdateError(''), 4000)
    }
  }, [])

  const totalAmount = invoices.reduce((s, i) => s + (i.amount_total || 0), 0)

  const pdfUrl = pdfInvoice ? getPdfUrl(pdfInvoice.id) : ''
  const isPdfImage = pdfInvoice ? /\.(jpe?g|png)$/i.test(pdfInvoice.pdf_filename ?? '') : false

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">

      {/* ── Left: PDF preview panel ── */}
      {pdfInvoice && (
        <div className="w-[45%] min-w-[360px] max-w-[700px] flex flex-col border-r border-gray-200 bg-white shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
            <span className="font-medium text-gray-800 text-sm truncate max-w-[60%]">
              {pdfInvoice.pdf_filename || 'Příloha'}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-400 select-none hidden sm:block">↑↓ navigace</span>
              <a href={pdfUrl} download={pdfInvoice.pdf_filename || 'priloha'}
                tabIndex={-1}
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                Stáhnout
              </a>
              <button onClick={() => setPdfInvoice(null)}
                title="Zavřít (Esc)"
                className="px-3 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">
                ✕ Zavřít
              </button>
            </div>
          </div>
          <div className="flex-1 bg-gray-100 overflow-hidden flex items-center justify-center">
            {isPdfImage ? (
              <img src={pdfUrl} alt={pdfInvoice.pdf_filename || 'příloha'}
                className="max-w-full max-h-full object-contain" />
            ) : (
              <iframe src={pdfUrl} className="w-full h-full" title="Náhled přílohy" tabIndex={-1} />
            )}
          </div>
        </div>
      )}

      {/* ── Right: main content ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
      {/* Navbar */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <img src="/logo.png" alt="Katerina Mlcakova" className="h-8 object-contain" />
        <div className="flex items-center gap-3">
          <button
            onClick={() => handleSync(false)}
            disabled={syncing}
            className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            {syncing ? 'Synchronizuji…' : 'Sync nové'}
          </button>
          <button
            onClick={() => handleSync(true)}
            disabled={syncing}
            className="px-3 py-1.5 text-xs border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 disabled:opacity-60 transition-colors"
          >
            {syncing ? 'Synchronizuji…' : 'Sync vše'}
          </button>
          <button
            onClick={() => navigate('/clients')}
            className="px-3 py-1.5 text-xs border border-green-600 text-green-700 rounded-lg hover:bg-green-50 transition-colors"
          >
            Adresář klientů
          </button>
          <button
            onClick={logout}
            className="px-3 py-1.5 text-xs text-gray-500 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Odhlásit
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {/* Status messages */}
        {liveMsg && (
          <div className="bg-blue-50 border border-blue-200 text-blue-800 text-sm rounded-lg px-4 py-2 flex items-center gap-2">
            <span className="animate-pulse w-2 h-2 bg-blue-500 rounded-full inline-block"></span>
            {liveMsg}
          </div>
        )}
        {syncMsg && (
          <div className="bg-green-50 border border-green-200 text-green-800 text-sm rounded-lg px-4 py-2">
            {syncMsg}
          </div>
        )}
        {updateError && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2">
            {updateError}
          </div>
        )}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2">
            {error}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Celkem faktur" value={String(invoices.length)} />
          <Stat label="Celková hodnota" value={fmtCzk(totalAmount)} />
          <Stat label="Úspěšně vytěženo" value={String(invoices.filter((i) => i.extraction_success).length)} />
          <Stat label="Bez PDF extrakce" value={String(invoices.filter((i) => !i.extraction_success).length)} />
        </div>

        {/* Filters */}
        <InvoiceFiltersBar
          filters={filters}
          onChange={setFilters}
          onReset={() => setFilters(DEFAULT_FILTERS)}
          clients={clients}
        />

        {/* Table */}
        {loading ? (
          <div className="text-center py-16 text-gray-500">Načítám faktury…</div>
        ) : (
          <InvoiceTable invoices={invoices} onPohodaExport={handlePohodaExport} onUpdate={handleUpdate} onPdfOpen={setPdfInvoice} activePdfId={pdfInvoice?.id ?? null} />
        )}
      </main>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-xl font-bold text-gray-800 mt-1">{value}</p>
    </div>
  )
}

function fmtCzk(v: number) {
  return new Intl.NumberFormat('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v) + ' Kč'
}
