#!/bin/sh
set -eu

mkdir -p /app/data/pdfs

export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/invoices.db}"
export PDF_STORAGE_PATH="${PDF_STORAGE_PATH:-/app/data/pdfs}"

nginx
exec uvicorn app.main:app --host 127.0.0.1 --port 8000