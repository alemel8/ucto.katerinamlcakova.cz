export type DocType = 'faktura' | 'faktura_prijata' | 'faktura_vydana' | 'uctenka' | 'dobropis' | 'jine'

export interface AresCompany {
  ico: string
  dic: string
  company_name: string
  street: string
  city: string
  zip: string
  full_address: string
  country: string
}

export interface Invoice {
  id: number
  email_uid: string
  email_uid_original: string | null
  attachment_index: number
  email_subject: string | null
  email_from: string | null
  email_date: string | null

  ico: string | null
  dic: string | null
  company_name: string | null
  supplier_address: string | null

  customer_name: string | null
  customer_ico: string | null
  customer_dic: string | null
  customer_address: string | null

  issue_date: string | null
  fulfillment_date: string | null
  due_date: string | null
  description: string | null

  amount_base_12: number | null
  amount_vat_12: number | null
  amount_base_21: number | null
  amount_vat_21: number | null
  amount_total: number | null

  pdf_filename: string | null
  invoice_number: string | null
  doc_type: DocType | null
  extraction_success: boolean
  extraction_notes: string | null
  created_at: string
}

export interface Client {
  id: number
  ico: string
  name: string | null
  created_at: string
}

export interface InvoiceFilters {
  search: string
  year: number | ''
  month: number | ''
  date_from: string
  date_to: string
  client_ico: string
}
