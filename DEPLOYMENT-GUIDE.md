# seil.space — Deployment Guide

**Standardní postup pro deploy jakékoli aplikace přes Coolify na VPS `seil.space`.**

Cílová skupina: ty (sám) v budoucnu, kdy si nebudeš pamatovat detaily. Otevři v VS Code, projdi krok po kroku.

---

## TL;DR — co se děje při běžném developmentu

```
[VS Code]                  [GitHub]              [Coolify]              [Live]
   │                          │                     │                     │
   ├─ edit code               │                     │                     │
   ├─ npm run dev (test)      │                     │                     │
   ├─ git commit              │                     │                     │
   └─ git push  ─────────►    ├─ webhook fire ─►    ├─ docker build       │
                              │                     ├─ container restart  │
                              │                     └─ HTTPS auto ────►   └─ live URL
```

**Push na `main` = nasazení.** Coolify má GitHub webhook, takže `git push` spustí build a deploy automaticky. Žádné ruční SSH na VPS.

---

## Infrastruktura — kde co je

| Komponenta | URL / cesta | Účel |
|---|---|---|
| **Coolify UI** | https://coolify.seil.space | Web management VPS aplikací |
| **VPS hostname** | seil.space (89.221.219.220) | Server, kde vše běží |
| **SSH** | `ssh ales@89.221.219.220` | Manuální správa, jen pro emergency |
| **PostgreSQL** | localhost:5432 (host), 172.18.x.x:5432 (Docker) | Sdílená DB pro aplikace |
| **Cloudflare DNS** | seil.space zóna | Subdomény pro infra a vlastní apps |
| **Wedos DNS** | klientské domény (.cz, .com) | Pro klientské weby |
| **GitHub** | github.com/alemel8 | Zdrojové repos |

---

## První nasazení nové aplikace — checklist

### A) Příprava GitHub repa

Každý repo musí mít:

- [ ] **`Dockerfile`** v rootu (viz [šablony níže](#dockerfile-šablony))
- [ ] **`package-lock.json`** / `poetry.lock` / equivalent (běž `npm install` lokálně)
- [ ] **`.env.example`** se seznamem env proměnných (bez hodnot!)
- [ ] **`README.md`** s krátkým popisem + Quick Start
- [ ] **`.gitignore`** — minimálně `node_modules/`, `.env`, `.env.local`, `data/*.json` (pokud používáš)
- [ ] **`.dockerignore`** — minimálně `node_modules/`, `.git/`, `.env*`, `*.md`, `.github/`

### B) Coolify projekt setup

V https://coolify.seil.space:

1. **Projects** → existing project (`production`, `staging`, `internal`) nebo **New Project**
2. **+ New Resource** → **Private Repository (with GitHub App)** *(nebo Public Repository)*
3. Vyber repo + branch (`main`)
4. **Build Pack:** Dockerfile *(Coolify detekuje automaticky)*
5. Continue → uvidíš konfigurační stránku

### C) Konfigurace v Coolify

**General tab:**

- **Name:** krátký jednoznačný název (např. `toneracek`, `grapenet`, …)
- **Domains:** `https://toneracek.cz` (jeden řádek per URL, `https://` důležité)
- **Direction:** Allow www & non-www (Coolify pak chytá obě varianty)
- **Ports Exposes:** interní port aplikace (Node.js typicky `3000`, Python `8000`)
- **Base Directory:** `/` (default)
- **Dockerfile Location:** `/Dockerfile` (default)
- Klik **Save**

**Environment Variables tab:**

- Pro každou proměnnou: **Add Variable** → Key + Value
- **Is Build Variable?** ❌ u všech proměnných pro tuto aplikaci; nic z nich není potřeba při `docker build`
- **Co zadat:**
    - `SECRET_KEY` = silný náhodný řetězec pro JWT; v produkci nepoužívat default z repa
    - `EMAIL_PASSWORD` = heslo k IMAP schránce, ze které se tahají faktury
    - `FRONTEND_PASSWORD` = heslo pro přihlášení do webu
    - `EMAIL_ADDRESS` = jen pokud se liší od `fakturace@katerinamlcakova.cz`
    - `FRONTEND_USERNAME` = jen pokud se liší od `fakturace@katerinamlcakova.cz`
    - `IMAP_HOST` a `IMAP_PORT` = jen pokud je schránka jinde než na Wedosu
    - `ALGORITHM` a `ACCESS_TOKEN_EXPIRE_MINUTES` = nech na defaultu, pokud nechceš měnit chování JWT
- **Nemusíš zadávat:** `DATABASE_URL` a `PDF_STORAGE_PATH` — image je už nastavuje na `/app/data`, pokud přidáš persistent storage
- Coolify auto-přidává: `COOLIFY_URL`, `COOLIFY_FQDN`, `COOLIFY_BRANCH` *(nemusíš)*

**Persistent Storage tab (jen pokud aplikace ukládá data lokálně):**

- **Add Storage**
- **Source:** `/var/lib/<jmeno-app>/data` (na hostu)
- **Destination:** `/app/data` (uvnitř kontejneru, podle aplikace)
- **Read-only:** ❌ ne (typicky chce zápis)

**Health Check tab (doporučeno):**

- **Enabled:** ✅
- **Path:** `/health` nebo `/api/health` (musí být v aplikaci implementováno)
- **Method:** GET
- **Expected Status:** 200
- **Interval:** 30 s

### D) DNS nastavení

**Pro doménu `*.seil.space`:**
- [dash.cloudflare.com](https://dash.cloudflare.com) → seil.space → DNS Records
- Add A record: `<subdomain>` → `89.221.219.220`, **DNS only (šedý mráček)**

**Pro klientské `.cz`/`.com` u Wedosu:**
- [client.wedos.com](https://client.wedos.com) → Domény → tvoje doména → DNS
- A záznam: `@` → `89.221.219.220`, TTL 300
- A záznam: `www` → `89.221.219.220`, TTL 300

**Pro klientskou doménu jinde (Forpsi, GoDaddy, Cloudflare):**
- Stejné A záznamy na 89.221.219.220 v jejich panelu

### E) První Deploy

1. Klik **Deploy** vpravo nahoře v Coolify UI
2. **Deployments** tab → sleduj live log
3. Trvá 2-10 minut (Docker build závisí na stacku)
4. Status změní na **Running** (zelené)

### F) Ověření

```bash
# DNS propagace:
dig +short @1.1.1.1 tvoje-domena.cz
# musi vratit: 89.221.219.220

# HTTPS:
curl -sI https://tvoje-domena.cz
# HTTP/2 200 nebo redirect

# V prohlizeci - aplikace funguje:
open https://tvoje-domena.cz
```

---

## Dockerfile šablony

### Next.js (App Router, standalone output)

```dockerfile
# Stage 1: Install deps
FROM node:20-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json* ./
RUN npm ci

# Stage 2: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Stage 3: Runtime
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Public assets first (standalone neobsahuje):
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Sharp pro Next.js image optimalizaci:
COPY --from=builder /app/node_modules/sharp ./node_modules/sharp
COPY --from=builder /app/node_modules/@img ./node_modules/@img

# Adresar pro persistent data:
RUN mkdir -p /app/data && chown nextjs:nodejs /app/data

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
```

Vyžaduje v `next.config.js`:
```js
module.exports = { output: 'standalone' }
```

### Node.js (Fastify / Express + EJS)

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -g 1001 -S app && adduser -S app -u 1001 -G app
COPY --from=deps --chown=app:app /app/node_modules ./node_modules
COPY --chown=app:app . .
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/server.js"]
```

### Python (FastAPI + Uvicorn)

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd -m -u 1001 app && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Statický web (Nginx)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

S `nginx.conf`:
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Environment Variables — best practices

### Kde

- **Production:** Coolify UI → tvoje app → Environment Variables
- **Lokální dev:** `.env` soubor v repu (NIKDY ho necommituj — `.gitignore` ho musí mít)
- **Šablona:** `.env.example` v repu (s placeholder hodnotami nebo komentáři)

### Build var vs runtime var

- **Build var (čekni "Is Build Variable?"):** Potřeba při `docker build` — typicky `NEXT_PUBLIC_*` v Next.js, někdy verze knihoven.
- **Runtime var:** Jen když kontejner běží — API klíče, DB credentials, SMTP passwords.

**Pravidlo:** API klíče **NEMAJÍ** být build vars. Build vars končí ve veřejně přístupném JS bundle (u Next.js).

### Secrets rotation

Pokud unikne secret (např. v logu, screenshotu, do gitu omylem):

1. **Rotuj v providerovi** (Stripe Dashboard → Roll secret, AWS → New IAM key, atd.)
2. **Aktualizuj v Coolify** env var
3. **Redeploy** aplikaci (Coolify → Redeploy)
4. **Smaž starou hodnotu** odkudkoliv ji můžeš dostat (chat, screenshoty)

---

## DNS přesměrování (přepnutí starý → nový server)

1. **Před změnou:** ulož TTL na 300 (5 minut) v Wedos panelu / Cloudflare
2. **Připrav Coolify deploy** — aplikace musí běžet a být dostupná přes auto-Coolify URL (`https://xxx.seil.space`)
3. **Změň A záznam** v DNS panelu domény → `89.221.219.220`
4. **Čekej propagaci** (5-30 minut, sledem `dig +short tvoje-domena.cz`)
5. **Coolify automaticky** vyžádá Let's Encrypt cert hned, jak DNS odpoví správně
6. **Po ověření, že vše jede**, můžeš TTL zpět nahoru (3600 nebo 14400)

---

## Persistent Storage — kdy a jak

### Kdy

- Aplikace ukládá uploady (obrázky, dokumenty)
- Aplikace má SQLite DB
- Konfigurace generovaná za běhu
- Lokální cache, kterou nechceš ztratit při redeploy

### Kdy NE

- Build artefakty (ty jsou v image)
- Logy (Coolify má vlastní log management)
- Temp files

### Konvence cest

| Aplikace | Host path | Container path |
|---|---|---|
| toneracek | `/var/lib/toneracek/data` | `/app/data` |
| grapenet | `/var/lib/grapenet/data` | `/app/data` |
| one.seil.space | `/var/lib/vps-stats` | `/var/lib/vps-stats` (RO) |

### Inicializace dat po prvním deployi

```bash
# Z Macu - nahrej soubor na VPS:
scp local-file.json ales@89.221.219.220:/tmp/

# Na VPS - presun do persistent volume + nastav owner:
ssh ales@89.221.219.220 '
sudo mkdir -p /var/lib/myapp/data
sudo mv /tmp/local-file.json /var/lib/myapp/data/
# Owner musi byt UID 1001 (nextjs/app user v kontejneru):
sudo chown -R 1001:1001 /var/lib/myapp/
'

# V Coolify UI: app → Restart (kontejner pak vidi nove soubory)
```

---

## PostgreSQL přístup z aplikace

**Host:** `host.docker.internal` *(z kontejneru se to mapuje na host)*
**Port:** `5432`
**User/password:** dle pg_dumpall obnovy — viz `/etc/postgresql/18/main/pg_hba.conf`

### Connection string template

```
postgresql://USER:PASSWORD@host.docker.internal:5432/DATABASE_NAME
```

### Dostupné databáze (po restore z původní VPS)

| DB | Použití |
|---|---|
| `seil` | Hlavní firemní DB |
| `grapenet` | Grapenet app |
| `alterna.energy` | Alterna Energy app |
| `brandborg-maritime` | Brandborg klient |
| `wellgo` | Wellgo / app.wellnessnadosah.cz |
| `TopDistribution` | Top-DB klient |
| `postgres` | Systémová |

### V Coolify env vars

```
DATABASE_URL=postgresql://user:pass@host.docker.internal:5432/dbname
```

---

## Day-2 operace v Coolify

### Logs

- Coolify UI → app → **Logs** tab
- Live tail, search, filter podle kontejneru

### Restart

- Coolify UI → app → **Restart** (nahoře vpravo)
- Restartuje kontejner bez rebuildu

### Redeploy

- Coolify UI → app → **Deploy** / **Redeploy**
- Stáhne nejnovější commit, rebuild image, restart

### Rollback

- Coolify UI → app → **Deployments** tab
- U starého úspěšného deploymentu klik **Redeploy this version**

### Scale (více instancí)

- Coolify UI → app → **Advanced** → **Replicas** = 2+
- Coolify vytvoří víc instancí, load balance přes Traefik

### Změna domény

- Coolify UI → app → **General** → **Domains** → upravit
- Save → Coolify se postará o nový SSL cert

---

## VS Code workflow

### Doporučená extension

- **GitLens** — better Git UX
- **Docker** — Dockerfile syntax, container management
- **REST Client** — testování API endpointů
- **Prisma** — pokud používáš Prisma ORM
- **GitHub Actions** — pokud máš CI

### Setup workspace per project

V VS Code:
1. **File → Open Folder** → vyber `~/Documents/Projects/<projekt>`
2. **Cmd+Shift+P** → "Terminal: Create New Terminal"
3. V terminálu:
   ```bash
   npm install         # nebo poetry install / pip install -r
   cp .env.example .env  # uprav hodnoty pro local dev
   npm run dev         # nebo equivalent
   ```
4. Otevři `http://localhost:3000` v prohlížeči

### Deploy cyklus

```bash
# 1. Uprav kod, otestuj lokalne
npm run dev

# 2. Commit + push - Coolify auto-deploy
git add -A
git commit -m "feat: něco"
git push origin main

# 3. Otevri Coolify UI v prohlizeci a sleduj deploy:
open https://coolify.seil.space
```

### Sledování logů přímo z VS Code terminálu

```bash
# Live logs z VPS:
ssh ales@89.221.219.220 'sudo docker logs -f $(docker ps --filter "name=tvoje-app" --format "{{.Names}}")'

# Posledni 100 radku:
ssh ales@89.221.219.220 'sudo docker logs --tail 100 $(docker ps --filter "name=tvoje-app" --format "{{.Names}}")'
```

---

## Troubleshooting — časté problémy

### "npm error code EUSAGE — npm ci requires package-lock.json"

→ Lokálně `npm install` (vygeneruje lock file) → commit + push.

### "COPY ... not found"

→ Dockerfile zkouší zkopírovat soubor, který je v `.gitignore`. Buď přidej do gitu, nebo použij Persistent Storage.

### "could not read Username for 'https://github.com'"

→ Repo je private a v Coolify není GitHub App. Buď udělej repo public, nebo přidej GitHub App v Coolify → Sources.

### Aplikace běží, ale doména vrací 502

→ Aplikace nezačala poslouchat na portu, který má v Coolify "Ports Exposes". Zkontroluj `PORT` env var a app `listen()` call.

### "DNS_PROBE_FINISHED_NXDOMAIN"

→ DNS záznam pro doménu neexistuje. Cloudflare → DNS Records → přidej A záznam na 89.221.219.220.

### "Let's Encrypt rate limit"

→ Pokud opakovaně testuješ deploy a Let's Encrypt zablokuje. Vypni HTTPS v Coolify dočasně, počkej hodinu, znova zapni.

### "Out of memory" během buildu

→ VPS má 4 GB RAM, Node build může toho potřebovat hodně. Coolify → app → **Advanced** → **Limits** → Memory: 1024M (pak víc, dle potřeby).

### Aplikace nemá přístup k Postgresu

→ Test connection: `ssh ales@... 'sudo -u postgres psql -h 172.18.0.1 -c "SELECT 1"'` — nejdřív ověř, že postgres poslouchá na Docker subnetu. Viz Postgres config v /etc/postgresql/18/main/postgresql.conf (`listen_addresses = '*'`) a pg_hba.conf.

---

## Bezpečnostní checklist před prvním produkčním deployem

- [ ] `.env` v `.gitignore` (NIKDY do gitu)
- [ ] Žádný plaintext secret v repu (ani v testech)
- [ ] Coolify env vars naplněné, žádné defaultní hodnoty
- [ ] Dockerfile používá non-root user (USER 1001 nebo podobné)
- [ ] Healthcheck endpoint **BEZ** auth (Coolify ho potřebuje volat)
- [ ] Backup strategie pro Persistent Storage (manuální nebo cron)
- [ ] DNS TTL nízký jen na chvíli kolem deployu, pak zpět
- [ ] DOMAIN má SSL (Coolify auto, jen ověř)
- [ ] Žádný citlivý log do stdout (Coolify Logs je viditelný admin)

---

## Reference: připojení do Coolify a VPS

```bash
# Coolify UI:
open https://coolify.seil.space

# SSH:
ssh ales@89.221.219.220

# PostgreSQL (z hostu):
ssh ales@89.221.219.220
sudo -u postgres psql

# Docker - běžící kontejnery:
ssh ales@89.221.219.220 'sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'

# Disk a paměť:
ssh ales@89.221.219.220 'df -h /; free -h'
```

---

## Existující projekty — stav

| App | Status | URL | Repo |
|---|---|---|---|
| one.seil.space | ✅ Production | https://one.seil.space | alemel8/one.seil.space |
| toneracek.cz | 🔧 In progress | https://toneracek.cz | alemel8/web.toneracek |
| grapenet | ⏳ TODO | grapenet.seil.cz | alemel8/app.grapenet |
| alterna-energy | ⏳ TODO | alterna-energy.seil.cz | alemel8/app.alterna-energy |
| wellgo | ⏳ TODO | app.wellnessnadosah.cz | alemel8/app.wellgo |
| katerinamlcakova | ⏳ TODO | ucto.katerinamlcakova.cz | (nezjištěno) |

---

## Verze tohoto guide

- **v1.0** — 2026-05-12 — Initial after migration from old VPS to Debian 12 + Coolify
