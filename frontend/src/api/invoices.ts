import api from './client'
import type { Invoice, InvoiceFilters, AresCompany, Client } from '../types/invoice'

export async function login(username: string, password: string): Promise<string> {
  const params = new URLSearchParams()
  params.append('username', username)
  params.append('password', password)
  const { data } = await api.post<{ access_token: string }>('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data.access_token
}

export async function fetchInvoices(filters: Partial<InvoiceFilters>): Promise<Invoice[]> {
  const params: Record<string, string> = {}
  if (filters.search) params.search = filters.search
  if (filters.year) params.year = String(filters.year)
  if (filters.month) params.month = String(filters.month)
  if (filters.date_from) params.date_from = filters.date_from
  if (filters.date_to) params.date_to = filters.date_to
  if (filters.client_ico) params.client_ico = filters.client_ico

  const { data } = await api.get<Invoice[]>('/invoices', { params })
  return data
}

export async function syncEmails(fetchAll = false): Promise<{ message: string; new_invoices: number; errors: number }> {
  const { data } = await api.post('/invoices/sync', null, { params: { fetch_all: fetchAll } })
  return data
}

export async function updateInvoice(id: number, payload: Partial<Invoice>): Promise<Invoice> {
  const { data } = await api.patch<Invoice>(`/invoices/${id}`, payload)
  return data
}

export function getPdfUrl(id: number): string {
  const token = localStorage.getItem('token')
  return `/api/invoices/${id}/pdf?token=${token}`
}

export async function fetchAresData(ico: string): Promise<AresCompany> {
  const { data } = await api.get<AresCompany>(`/ares/${ico}`)
  return data
}

export function getPohodaExportUrl(ids?: number[]): string {
  const token = localStorage.getItem('token')
  const idParam = ids && ids.length > 0 ? `&ids=${ids.join(',')}` : ''
  return `/api/invoices/export/pohoda?token=${token}${idParam}`
}

export async function fetchClients(): Promise<Client[]> {
  const { data } = await api.get<Client[]>('/clients')
  return data
}

export async function createClient(ico: string, name?: string): Promise<Client> {
  const { data } = await api.post<Client>('/clients', { ico, name: name ?? null })
  return data
}

export async function updateClient(id: number, ico: string, name?: string): Promise<Client> {
  const { data } = await api.put<Client>(`/clients/${id}`, { ico, name: name ?? null })
  return data
}

export async function deleteClient(id: number): Promise<void> {
  await api.delete(`/clients/${id}`)
}
