import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchClients, createClient, updateClient, deleteClient, fetchAresData } from '../api/invoices'
import type { Client } from '../types/invoice'

export default function ClientDirectory() {
  const navigate = useNavigate()
  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // New/edit form state
  const [showForm, setShowForm] = useState(false)
  const [editClient, setEditClient] = useState<Client | null>(null)
  const [formIco, setFormIco] = useState('')
  const [formName, setFormName] = useState('')
  const [formLoading, setFormLoading] = useState(false)
  const [formError, setFormError] = useState('')
  const [aresLookupLoading, setAresLookupLoading] = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      setClients(await fetchClients())
    } catch {
      setError('Chyba při načítání klientů')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function openAdd() {
    setEditClient(null)
    setFormIco('')
    setFormName('')
    setFormError('')
    setShowForm(true)
  }

  function openEdit(c: Client) {
    setEditClient(c)
    setFormIco(c.ico)
    setFormName(c.name ?? '')
    setFormError('')
    setShowForm(true)
  }

  async function lookupAres() {
    if (formIco.length !== 8) return
    setAresLookupLoading(true)
    setFormError('')
    try {
      const data = await fetchAresData(formIco)
      setFormName(data.company_name)
    } catch {
      setFormError('Subjekt nenalezen v ARES')
    } finally {
      setAresLookupLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormLoading(true)
    setFormError('')
    try {
      if (editClient) {
        const updated = await updateClient(editClient.id, formIco, formName || undefined)
        setClients(prev => prev.map(c => c.id === updated.id ? updated : c))
      } else {
        const created = await createClient(formIco, formName || undefined)
        setClients(prev => [...prev, created].sort((a, b) => (a.name ?? a.ico).localeCompare(b.name ?? b.ico)))
      }
      setShowForm(false)
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      setFormError(msg ?? 'Chyba při ukládání klienta')
    } finally {
      setFormLoading(false)
    }
  }

  async function handleDelete(c: Client) {
    if (!confirm(`Opravdu smazat klienta ${c.name ?? c.ico}?`)) return
    try {
      await deleteClient(c.id)
      setClients(prev => prev.filter(x => x.id !== c.id))
    } catch {
      setError('Chyba při mazání klienta')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-gray-500 hover:text-gray-800 text-sm transition-colors"
          >
            ← Zpět
          </button>
          <h1 className="text-lg font-bold text-gray-900">Adresář klientů</h1>
        </div>
        <button
          onClick={openAdd}
          className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          + Přidat klienta
        </button>
      </header>

      <main className="px-6 py-5 max-w-3xl mx-auto">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2 mb-4">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-16 text-gray-500">Načítám klienty…</div>
        ) : clients.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            Žádní klienti. Přidejte prvního kliknutím na „+ Přidat klienta".
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Název</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">IČ</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600 w-24"></th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c, idx) => (
                  <tr
                    key={c.id}
                    className={idx % 2 === 0 ? 'border-t border-gray-100' : 'border-t border-gray-100 bg-gray-50/50'}
                  >
                    <td className="px-4 py-3 text-gray-800">{c.name ?? <span className="text-gray-400 italic">—</span>}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono">{c.ico}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => openEdit(c)}
                          className="text-xs text-blue-600 hover:text-blue-800 transition-colors"
                        >
                          Upravit
                        </button>
                        <button
                          onClick={() => handleDelete(c)}
                          className="text-xs text-red-500 hover:text-red-700 transition-colors"
                        >
                          Smazat
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {/* Add/Edit modal */}
      {showForm && (
        <>
          <div className="fixed inset-0 bg-black/30 z-40" onClick={() => setShowForm(false)} />
          <div className="fixed inset-0 flex items-center justify-center z-50 px-4">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm">
              <h2 className="text-base font-bold text-gray-800 mb-4">
                {editClient ? 'Upravit klienta' : 'Přidat klienta'}
              </h2>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">IČ *</label>
                  <div className="flex gap-2">
                    <input
                      required
                      value={formIco}
                      onChange={e => setFormIco(e.target.value.replace(/\D/g, '').slice(0, 8))}
                      placeholder="12345678"
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                    />
                    <button
                      type="button"
                      onClick={lookupAres}
                      disabled={formIco.length !== 8 || aresLookupLoading}
                      className="px-3 py-1.5 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded-lg hover:bg-purple-100 disabled:opacity-50 transition-colors whitespace-nowrap"
                    >
                      {aresLookupLoading ? 'Načítám…' : 'ARES'}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Název</label>
                  <input
                    value={formName}
                    onChange={e => setFormName(e.target.value)}
                    placeholder="Název firmy"
                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                {formError && (
                  <p className="text-red-600 text-xs">{formError}</p>
                )}
                <div className="flex gap-2 pt-1">
                  <button
                    type="submit"
                    disabled={formLoading}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg py-2 transition-colors"
                  >
                    {formLoading ? 'Ukládám…' : 'Uložit'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="flex-1 border border-gray-300 text-gray-600 text-sm rounded-lg py-2 hover:bg-gray-50 transition-colors"
                  >
                    Zrušit
                  </button>
                </div>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
