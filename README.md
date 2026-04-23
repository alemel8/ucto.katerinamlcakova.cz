# Vytěžování faktur

Aplikace pro automatické vytěžování faktur z e-mailové schránky s webovým frontendem.

## Architektura

- **Backend**: Python FastAPI + SQLite — API server, IMAP sync, PDF extrakce
- **Frontend**: React + TypeScript + Tailwind CSS — webové rozhraní
- **Nginx**: reverzní proxy
- **Docker Compose**: orchestrace

## Spuštění (lokální vývoj)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend bude na http://localhost:5173 a automaticky proxuje `/api` na backend (:8000).

## Spuštění na VPS (Docker)

```bash
git clone <repo> vytezovani-faktur
cd vytezovani-faktur

# Upravte hesla v backend/.env
docker compose up -d --build
```
Aplikace poběží na portu 80.

## Přihlášení

- **URL**: http://<vps-ip>/
- **Uživatel**: `fakturace@katerinamlcakova.cz`
- **Heslo**: `Nikola19`

## Funkce

- Automatická synchronizace e-mailů každé 2 minuty (IMAP polling)
- Extrakce dat z PDF: IČ, DIČ, firma, data, předmět plnění, částky
- Tabulka seskupená po měsících s filtry
- Náhled a stažení PDF příloh
- Export do formátu XML pro účetní systém POHODA

## POHODA export

V pravém horním rohu klikněte na **Export POHODA (vše)** nebo vyberte faktury zaškrtávacím políčkem a klikněte **Export do POHODA**. Vygeneruje se soubor `pohoda_export.xml` ve formátu POHODA XML 2.0 (přijaté faktury).

## Struktura projektu

```
vytezovani-faktur/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── main.py           # Aplikace, scheduler
│   │   ├── config.py         # Konfigurace (.env)
│   │   ├── models.py         # SQLAlchemy modely
│   │   ├── email_fetcher.py  # IMAP stahování
│   │   ├── pdf_extractor.py  # Extrakce dat z PDF
│   │   └── routers/          # API endpointy
│   └── requirements.txt
├── frontend/         # React frontend
│   └── src/
│       ├── components/       # UI komponenty
│       └── api/              # API klient
├── nginx/            # Nginx konfigurace
└── docker-compose.yml
```
