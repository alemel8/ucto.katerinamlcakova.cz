import logging
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from .database import engine, Base, SessionLocal
from .routers import auth, invoices, ares
from .email_fetcher import EmailFetcher, ImapIdleWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

# ─── WebSocket connection manager ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: str):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self.active -= dead


ws_manager = ConnectionManager()


# ─── Background jobs ──────────────────────────────────────────────────────────

def scheduled_sync():
    """Fallback background job: fetch any missed emails every 5 minutes."""
    db = SessionLocal()
    try:
        fetcher = EmailFetcher()
        result = fetcher.sync(db, fetch_all=False)
        if result["new_invoices"] > 0:
            logger.info(f"Scheduled sync: {result['new_invoices']} new invoices")
            import asyncio
            loop = getattr(scheduled_sync, "_loop", None)
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast("new_invoice"), loop
                )
    except Exception as e:
        logger.error(f"Scheduled sync error: {e}")
    finally:
        db.close()


def _make_idle_db_factory_with_notify(loop):
    """Wrap SessionLocal so IDLE watcher can notify WebSocket clients after save."""
    from .database import SessionLocal as SL

    class NotifyingSession(SL.__class__):
        pass

    # We patch EmailFetcher._process_email indirectly via a wrapper db
    return SL


scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_sync, "interval", minutes=5, id="email_sync")

idle_watcher = ImapIdleWatcher(db_factory=SessionLocal)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    loop = asyncio.get_event_loop()
    scheduled_sync._loop = loop

    # Wire real-time WebSocket notification from IDLE watcher
    def notify_clients():
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast("new_invoice"), loop)

    idle_watcher.on_new_invoice = notify_clients
    idle_watcher.start()
    scheduler.start()
    logger.info("IMAP IDLE watcher + fallback scheduler (5 min) started")
    yield
    idle_watcher.stop()
    scheduler.shutdown()


app = FastAPI(
    title="Vytěžování faktur",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(ares.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive (ping frames)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/health")
def health():
    return {"status": "ok"}
