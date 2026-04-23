import { useState, useMemo, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type OnChangeFn,
} from '@tanstack/react-table'
import { format, parseISO } from 'date-fns'
import { cs } from 'date-fns/locale'
import type { Invoice, DocType, AresCompany } from '../types/invoice'
import { fetchAresData } from '../api/invoices'

// ─── Module-level ARES cache ──────────────────────────────────────────────────
const _aresCache = new Map<string, AresCompany | null>()
const _aresInFlight = new Set<string>()

const col = createColumnHelper<Invoice>()

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(d: string | null) {
  if (!d) return '–'
  try { return format(parseISO(d), 'd.M.yyyy') } catch { return d }
}

function fmtAmt(v: number | null) {
  if (v === null || v === undefined) return '–'
  return new Intl.NumberFormat('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v) + ' Kč'
}

function monthKey(inv: Invoice): string {
  const dateStr = inv.issue_date || inv.email_date
  if (!dateStr) return '0000-00'
  try { return format(parseISO(dateStr), 'yyyy-MM') } catch { return '0000-00' }
}

function monthLabel(key: string): string {
  if (key === '0000-00') return 'Neznámý datum'
  try { return format(parseISO(key + '-01'), 'LLLL yyyy', { locale: cs }) } catch { return key }
}

// ─── DocTypeBadge ─────────────────────────────────────────────────────────────
const DOC_TYPE_LABELS: Record<DocType, string> = {
  faktura:         'Faktura',           // backward compat for old rows
  faktura_prijata: 'Faktura přijatá',
  faktura_vydana:  'Faktura vydaná',
  uctenka:         'Účtenka',
  dobropis:        'Dobropis',
  jine:            'Jiné',
}

const DOC_TYPE_COLORS: Record<DocType, string> = {
  faktura:         'bg-blue-100 text-blue-800 border-blue-200',
  faktura_prijata: 'bg-blue-100 text-blue-800 border-blue-200',
  faktura_vydana:  'bg-indigo-100 text-indigo-800 border-indigo-200',
  uctenka:         'bg-amber-100 text-amber-800 border-amber-200',
  dobropis:        'bg-red-100 text-red-800 border-red-200',
  jine:            'bg-gray-100 text-gray-600 border-gray-200',
}

function DocTypeBadge({ value }: { value: DocType | null }) {
  const dt = (value ?? 'jine') as DocType
  const label = DOC_TYPE_LABELS[dt] ?? value ?? 'Jiné'
  const color = DOC_TYPE_COLORS[dt] ?? DOC_TYPE_COLORS['jine']
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap ${color}`}>
      {label}
    </span>
  )
}

// ─── EditableDocType ──────────────────────────────────────────────────────────
function EditableDocType({
  value, invoiceId, onUpdate,
}: {
  value: DocType | null
  invoiceId: number
  onUpdate: (id: number, patch: Record<string, unknown>) => void
}) {
  const [editing, setEditing] = useState(false)
  // Guard: onChange must fire before onBlur closes the select
  const didChangeRef = useRef(false)

  if (editing) {
    return (
      <select
        autoFocus
        defaultValue={value || 'jine'}
        onChange={e => {
          didChangeRef.current = true
          onUpdate(invoiceId, { doc_type: e.target.value })
          setEditing(false)
        }}
        onBlur={() => {
          if (!didChangeRef.current) setEditing(false)
          didChangeRef.current = false
        }}
        className="border border-blue-400 rounded text-xs p-0.5 focus:outline-none bg-white min-w-[130px]"
      >
        <option value="faktura_prijata">Faktura přijatá</option>
        <option value="faktura_vydana">Faktura vydaná</option>
        <option value="uctenka">Účtenka</option>
        <option value="dobropis">Dobropis</option>
        <option value="jine">Jiné</option>
      </select>
    )
  }
  return (
    <span onClick={() => setEditing(true)} className="cursor-pointer" title="Klikněte pro úpravu">
      <DocTypeBadge value={value} />
    </span>
  )
}

// ─── EditableCell (text / number / date) ──────────────────────────────────────
function EditableCell({
  value, display, invoiceId, field, onUpdate, type = 'text', className,
}: {
  value: string | number | null
  display?: string
  invoiceId: number
  field: string
  onUpdate: (id: number, patch: Record<string, unknown>) => void
  type?: 'text' | 'number' | 'date'
  className?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  function startEdit() {
    let raw = value === null || value === undefined ? '' : String(value)
    if (type === 'date' && raw) raw = raw.substring(0, 10)
    setDraft(raw)
    setEditing(true)
  }

  function commit() {
    setEditing(false)
    let parsed: string | number | null = null
    if (draft !== '') {
      if (type === 'number') {
        const normalized = draft.replace(',', '.').replace(/\s/g, '')
        parsed = isNaN(Number(normalized)) ? null : Number(normalized)
      } else {
        parsed = draft
      }
    }
    const original = value === null || value === undefined ? null : value
    if (parsed !== original) onUpdate(invoiceId, { [field]: parsed })
  }

  if (editing) {
    return (
      <input
        autoFocus
        type={type === 'date' ? 'date' : 'text'}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') setEditing(false)
        }}
        className={`w-full min-w-[80px] border border-blue-400 rounded px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 bg-blue-50 ${className || ''}`}
      />
    )
  }

  const shown = display ?? (value !== null && value !== undefined && value !== '' ? String(value) : '–')
  return (
    <span
      onClick={startEdit}
      title="Klikněte pro úpravu"
      className={`cursor-pointer hover:bg-amber-50 hover:outline hover:outline-1 hover:outline-amber-300 rounded px-0.5 -mx-0.5 transition-colors ${className || ''}`}
    >
      {shown}
    </span>
  )
}

// ─── CompanyCell (ARES tooltip + edit popover) ────────────────────────────────
interface CompanyCellProps {
  name: string | null
  ico: string | null
  dic: string | null
  address: string | null
  invoiceId: number
  fields: { name: string; ico: string; dic: string; address: string }
  onUpdate: (id: number, patch: Record<string, unknown>) => void
}

function CompanyCell({ name, ico, dic, address, invoiceId, fields, onUpdate }: CompanyCellProps) {
  const anchorRef = useRef<HTMLDivElement>(null)

  const [tooltipCoords, setTooltipCoords] = useState<{ x: number; y: number } | null>(null)
  const [aresData, setAresData] = useState<AresCompany | null>(
    ico ? (_aresCache.has(ico) ? (_aresCache.get(ico) ?? null) : null) : null,
  )
  // Track the ICO for which aresData was last loaded
  const [aresLoadedForIco, setAresLoadedForIco] = useState<string | null>(
    ico && _aresCache.has(ico) && _aresCache.get(ico) !== null ? ico : null,
  )
  const [aresLoading, setAresLoading] = useState(false)
  const [aresError, setAresError] = useState('')

  const [editPos, setEditPos] = useState<{ top: number; left: number } | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftIco, setDraftIco] = useState('')
  const [draftDic, setDraftDic] = useState('')
  const [draftAddress, setDraftAddress] = useState('')

  useEffect(() => {
    if (!editPos) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setEditPos(null) }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [editPos])

  function loadAres(icoVal: string) {
    setAresError('')
    if (_aresCache.has(icoVal)) {
      const cached = _aresCache.get(icoVal) ?? null
      setAresData(cached)
      setAresLoadedForIco(icoVal)
      if (!cached) setAresError('Subjekt nenalezen v ARES')
      return
    }
    if (_aresInFlight.has(icoVal)) return
    _aresInFlight.add(icoVal)
    setAresLoading(true)
    fetchAresData(icoVal)
      .then(data => { _aresCache.set(icoVal, data); setAresData(data); setAresLoadedForIco(icoVal) })
      .catch(() => {
        _aresCache.set(icoVal, null)
        setAresData(null)
        setAresLoadedForIco(icoVal)
        setAresError('Subjekt nenalezen v ARES')
      })
      .finally(() => { _aresInFlight.delete(icoVal); setAresLoading(false) })
  }

  function handleMouseEnter(e: React.MouseEvent) {
    setTooltipCoords({ x: e.clientX, y: e.clientY })
    if (ico) loadAres(ico)
  }

  function openEdit() {
    setDraftName(name || '')
    setDraftIco(ico || '')
    setDraftDic(dic || '')
    setDraftAddress(address || '')
    setAresError('')
    setTooltipCoords(null)
    if (anchorRef.current) {
      const r = anchorRef.current.getBoundingClientRect()
      setEditPos({ top: r.bottom + 6, left: r.left })
    }
  }

  function applyAres() {
    if (!aresData) return
    setDraftName(aresData.company_name)
    setDraftIco(aresData.ico)
    setDraftDic(aresData.dic)
    setDraftAddress(aresData.full_address)
  }

  function save() {
    onUpdate(invoiceId, {
      [fields.name]: draftName || null,
      [fields.ico]: draftIco || null,
      [fields.dic]: draftDic || null,
      [fields.address]: draftAddress || null,
    })
    setEditPos(null)
  }

  const display = name || '–'

  const tooltipLines = aresData
    ? [
        aresData.ico ? `IČ: ${aresData.ico}` : null,
        aresData.dic ? `DIČ: ${aresData.dic}` : null,
        aresData.full_address || null,
      ].filter(Boolean) as string[]
    : [
        ico ? `IČ: ${ico}` : null,
        dic ? `DIČ: ${dic}` : null,
        address || null,
      ].filter(Boolean) as string[]

  return (
    <div ref={anchorRef} className="inline-flex items-center gap-1 max-w-[160px] group/company">
      <span
        onMouseEnter={handleMouseEnter}
        onMouseMove={e => setTooltipCoords({ x: e.clientX, y: e.clientY })}
        onMouseLeave={() => setTooltipCoords(null)}
        className="truncate text-gray-800 cursor-default"
        title={display}
      >
        {display}
      </span>
      <button
        onClick={openEdit}
        className="shrink-0 text-gray-300 hover:text-blue-500 opacity-0 group-hover/company:opacity-100 transition-all text-[11px] leading-none"
        title="Upravit"
      >
        ✏
      </button>

      {/* ARES tooltip */}
      {tooltipCoords && !editPos && createPortal(
        <div
          style={{
            position: 'fixed',
            top: tooltipCoords.y - 10,
            left: tooltipCoords.x,
            transform: 'translate(-50%, -100%)',
            zIndex: 9999,
            pointerEvents: 'none',
          }}
          className="bg-gray-900 text-white text-xs rounded-lg shadow-2xl p-3 min-w-[200px] max-w-xs whitespace-normal"
        >
          {aresLoading && <div className="text-gray-400 animate-pulse">Načítám z ARES…</div>}
          {!aresLoading && (
            <>
              {tooltipLines.length > 0
                ? tooltipLines.map((l, i) => <div key={i} className={i > 0 ? 'mt-0.5' : ''}>{l}</div>)
                : <div className="text-gray-500">Žádné informace</div>
              }
              {aresData && (
                <div className="mt-1 pt-1 border-t border-gray-700 text-[10px] text-green-400">
                  ✓ Obohaceno z ARES
                </div>
              )}
            </>
          )}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-[5px] border-transparent border-t-gray-900" />
        </div>,
        document.body,
      )}

      {/* Edit popover */}
      {editPos && createPortal(
        <>
          <div className="fixed inset-0 z-[9998]" onClick={() => setEditPos(null)} />
          <div
            style={{ position: 'fixed', top: editPos.top, left: editPos.left, zIndex: 9999 }}
            className="bg-white border border-gray-200 rounded-xl shadow-2xl p-4 w-80"
          >
            <div className="text-sm font-semibold text-gray-800 mb-3">Upravit informace</div>

            <label className="block text-xs text-gray-500 mb-1">Název firmy</label>
            <input value={draftName} onChange={e => setDraftName(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs mb-2 focus:outline-none focus:border-blue-400"
            />

            <div className="flex gap-2">
              <div className="flex-1">
                <label className="block text-xs text-gray-500 mb-1">IČO</label>
                <input value={draftIco} onChange={e => setDraftIco(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs mb-2 focus:outline-none focus:border-blue-400"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs text-gray-500 mb-1">DIČ</label>
                <input value={draftDic} onChange={e => setDraftDic(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs mb-2 focus:outline-none focus:border-blue-400"
                />
              </div>
            </div>

            <label className="block text-xs text-gray-500 mb-1">Fakturační adresa</label>
            <input value={draftAddress} onChange={e => setDraftAddress(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs mb-3 focus:outline-none focus:border-blue-400"
            />

            <div className="flex items-center gap-2 flex-wrap">
              {/* Show Vyhledat when draftIco is 8 digits and different from what's already loaded */}
              {draftIco.length === 8 && draftIco !== aresLoadedForIco && (
                <button onClick={() => loadAres(draftIco)} disabled={aresLoading}
                  className="px-2 py-1 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded-lg hover:bg-purple-100 disabled:opacity-50 transition-colors"
                >
                  {aresLoading ? 'Načítám…' : 'Vyhledat v ARES'}
                </button>
              )}
              {aresData && aresLoadedForIco === draftIco && (
                <button onClick={applyAres}
                  className="px-2 py-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                >
                  ↓ Doplnit z ARES
                </button>
              )}
              {aresError && (
                <span className="text-red-500 text-[10px]">{aresError}</span>
              )}
              <button onClick={save}
                className="px-3 py-1 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Uložit
              </button>
              <button onClick={() => setEditPos(null)}
                className="px-3 py-1 text-xs text-gray-500 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Zrušit
              </button>
            </div>
          </div>
        </>,
        document.body,
      )}
    </div>
  )
}

// ─── InvoiceTable ─────────────────────────────────────────────────────────────
interface Props {
  invoices: Invoice[]
  onPohodaExport: (ids: number[]) => void
  onUpdate: (id: number, patch: Record<string, unknown>) => void
  onPdfOpen: (inv: Invoice) => void
  activePdfId?: number | null
}

export default function InvoiceTable({ invoices, onPohodaExport, onUpdate, onPdfOpen, activePdfId }: Props) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [collapsedMonths, setCollapsedMonths] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const columns = useMemo(
    () => [
      col.display({
        id: 'select',
        header: ({ table }) => (
          <input type="checkbox" checked={table.getIsAllRowsSelected()}
            onChange={table.getToggleAllRowsSelectedHandler()} className="rounded" />
        ),
        cell: ({ row }) => (
          <input type="checkbox" checked={selectedIds.has(row.original.id)}
            onChange={() => toggleSelect(row.original.id)} className="rounded" />
        ),
      }),

      // Příloha — icon button, BEFORE Typ
      col.display({
        id: 'pdf', header: '',
        cell: ({ row }) => row.original.pdf_filename ? (
          <button
            onClick={() => onPdfOpen(row.original)}
            title={row.original.pdf_filename}
            className="text-gray-400 hover:text-blue-600 transition-colors text-base leading-none"
          >
            📎
          </button>
        ) : <span className="text-gray-200 text-base leading-none select-none">📎</span>,
      }),

      col.display({
        id: 'doc_type',
        header: 'Typ',
        cell: ({ row }) => (
          <EditableDocType value={row.original.doc_type} invoiceId={row.original.id} onUpdate={onUpdate} />
        ),
      }),

      col.display({
        id: 'dodavatel',
        header: 'Dodavatel',
        cell: ({ row }) => {
          const inv = row.original
          return (
            <CompanyCell name={inv.company_name} ico={inv.ico} dic={inv.dic} address={inv.supplier_address}
              invoiceId={inv.id} fields={{ name: 'company_name', ico: 'ico', dic: 'dic', address: 'supplier_address' }}
              onUpdate={onUpdate} />
          )
        },
      }),

      col.display({
        id: 'odberatel',
        header: 'Odběratel',
        cell: ({ row }) => {
          const inv = row.original
          return (
            <CompanyCell name={inv.customer_name} ico={inv.customer_ico} dic={inv.customer_dic} address={inv.customer_address}
              invoiceId={inv.id} fields={{ name: 'customer_name', ico: 'customer_ico', dic: 'customer_dic', address: 'customer_address' }}
              onUpdate={onUpdate} />
          )
        },
      }),

      col.display({
        id: 'issue_date', header: 'Datum vystavení',
        cell: ({ row }) => <EditableCell value={row.original.issue_date} display={fmt(row.original.issue_date)}
          invoiceId={row.original.id} field="issue_date" type="date" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'fulfillment_date', header: 'Datum plnění',
        cell: ({ row }) => <EditableCell value={row.original.fulfillment_date} display={fmt(row.original.fulfillment_date)}
          invoiceId={row.original.id} field="fulfillment_date" type="date" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'due_date', header: 'Datum splatnosti',
        cell: ({ row }) => <EditableCell value={row.original.due_date} display={fmt(row.original.due_date)}
          invoiceId={row.original.id} field="due_date" type="date" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'description', header: 'Předmět plnění',
        cell: ({ row }) => <EditableCell value={row.original.description} invoiceId={row.original.id}
          field="description" type="text" onUpdate={onUpdate} className="max-w-48 block truncate" />,
      }),
      col.display({
        id: 'amount_base_12', header: 'Základ 12 %',
        cell: ({ row }) => <EditableCell value={row.original.amount_base_12} display={fmtAmt(row.original.amount_base_12)}
          invoiceId={row.original.id} field="amount_base_12" type="number" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'amount_vat_12', header: 'DPH 12 %',
        cell: ({ row }) => <EditableCell value={row.original.amount_vat_12} display={fmtAmt(row.original.amount_vat_12)}
          invoiceId={row.original.id} field="amount_vat_12" type="number" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'amount_base_21', header: 'Základ 21 %',
        cell: ({ row }) => <EditableCell value={row.original.amount_base_21} display={fmtAmt(row.original.amount_base_21)}
          invoiceId={row.original.id} field="amount_base_21" type="number" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'amount_vat_21', header: 'DPH 21 %',
        cell: ({ row }) => <EditableCell value={row.original.amount_vat_21} display={fmtAmt(row.original.amount_vat_21)}
          invoiceId={row.original.id} field="amount_vat_21" type="number" onUpdate={onUpdate} />,
      }),
      col.display({
        id: 'amount_total', header: 'Celkem',
        cell: ({ row }) => <EditableCell value={row.original.amount_total} display={fmtAmt(row.original.amount_total)}
          invoiceId={row.original.id} field="amount_total" type="number" onUpdate={onUpdate} className="font-semibold" />,
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedIds, onUpdate, onPdfOpen],
  )

  const grouped = useMemo(() => {
    const map = new Map<string, Invoice[]>()
    for (const inv of invoices) {
      const key = monthKey(inv)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(inv)
    }
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0]))
  }, [invoices])

  function toggleSelect(id: number) {
    setSelectedIds((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next })
  }

  function toggleMonth(key: string) {
    setCollapsedMonths((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next })
  }

  function monthTotal(invs: Invoice[]) {
    return invs.reduce((s, i) => s + (i.amount_total || 0), 0)
  }

  if (invoices.length === 0) {
    return <div className="text-center py-16 text-gray-500">Žádné faktury nenalezeny.</div>
  }

  return (
    <>
      {selectedIds.size > 0 && (
        <div className="mb-3 flex items-center gap-3">
          <span className="text-sm text-gray-600">{selectedIds.size} faktur vybráno</span>
          <button onClick={() => onPohodaExport(Array.from(selectedIds))}
            className="px-4 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors">
            Export do POHODA
          </button>
          <button onClick={() => setSelectedIds(new Set())} className="text-sm text-gray-500 hover:text-gray-700">
            Zrušit výběr
          </button>
        </div>
      )}

      <div className="space-y-4">
        {grouped.map(([key, groupInvs]) => (
          <MonthGroup key={key} monthKey={key} invoices={groupInvs} columns={columns}
            sorting={sorting} onSortingChange={setSorting}
            collapsed={collapsedMonths.has(key)} onToggle={() => toggleMonth(key)}
            total={monthTotal(groupInvs)} activePdfId={activePdfId} />
        ))}
      </div>

    </>
  )
}

// ─── MonthGroup ───────────────────────────────────────────────────────────────
interface MonthGroupProps {
  monthKey: string
  invoices: Invoice[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: any[]
  sorting: SortingState
  onSortingChange: OnChangeFn<SortingState>
  collapsed: boolean
  onToggle: () => void
  total: number
  activePdfId?: number | null
}

function MonthGroup({ monthKey: key, invoices, columns, sorting, onSortingChange, collapsed, onToggle, total, activePdfId }: MonthGroupProps) {
  // Scroll active row into view when activePdfId changes
  useEffect(() => {
    if (!activePdfId) return
    const el = document.querySelector<HTMLElement>(`tr[data-invoice-id="${activePdfId}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [activePdfId])
  const table = useReactTable({
    data: invoices,
    columns,
    state: { sorting },
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-800 capitalize">
            {monthLabel(key)}
          </span>
          <span className="text-xs text-gray-500 bg-gray-200 rounded-full px-2 py-0.5">
            {invoices.length} faktur
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-gray-700">{fmtAmt(total)}</span>
          <span className="text-gray-400 text-xs">{collapsed ? '▶' : '▼'}</span>
        </div>
      </button>

      {/* Table */}
      {!collapsed && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="bg-gray-50 border-t border-gray-100">
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      onClick={header.column.getToggleSortingHandler()}
                      className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap select-none cursor-pointer hover:bg-gray-100"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === 'asc' && ' ↑'}
                      {header.column.getIsSorted() === 'desc' && ' ↓'}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, idx) => {
                const isActive = row.original.id === activePdfId
                return (
                  <tr
                    key={row.id}
                    data-invoice-id={row.original.id}
                    className={[
                      'border-t border-gray-100 transition-colors',
                      isActive
                        ? 'bg-blue-100 ring-1 ring-inset ring-blue-400'
                        : idx % 2 === 0 ? 'hover:bg-blue-50/40' : 'bg-gray-50/50 hover:bg-blue-50/40',
                    ].join(' ')}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2 whitespace-nowrap text-gray-700">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
