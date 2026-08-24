from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .db import init_db
from .importer import parse_file
from . import repository as repo
from .telegram_service import telegram_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        await telegram_service.start()
    except Exception as exc:
        print("Telegram bot did not start:", exc)
    yield
    await telegram_service.stop()


app = FastAPI(title="Debt Collector", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    debt_amount: int = Field(ge=0)
    external_id: Optional[str] = None


class CustomerPatch(BaseModel):
    name: Optional[str] = None
    debt_amount: Optional[int] = Field(default=None, ge=0)
    telegram_chat_id: Optional[str] = None
    telegram_group_title: Optional[str] = None
    status: Optional[str] = None


class ImportRow(BaseModel):
    external_id: Optional[str] = None
    name: str
    debt_amount: int = Field(ge=0)


class ImportCommit(BaseModel):
    filename: str
    file_type: str
    rows: list[ImportRow]


class PromisePatch(BaseModel):
    status: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard():
    return repo.dashboard()


@app.get("/api/customers")
def customers(search: str = "", status: str = ""):
    return repo.list_customers(search, status)


@app.post("/api/customers")
def create_customer(payload: CustomerCreate):
    cid, _ = repo.upsert_customer(payload.name, payload.debt_amount, payload.external_id)
    return repo.get_customer(cid)


@app.patch("/api/customers/{customer_id}")
def patch_customer(customer_id: int, payload: CustomerPatch):
    if not repo.get_customer(customer_id):
        raise HTTPException(404, "مشتری پیدا نشد")
    return repo.update_customer(customer_id, payload.model_dump(exclude_unset=True))


@app.post("/api/customers/{customer_id}/send")
async def send_customer(customer_id: int):
    try:
        await telegram_service.send_collection_message(customer_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/followups/start")
async def start_followups():
    sent, skipped, errors = 0, 0, []
    for c in repo.list_customers():
        if c["debt_amount"] <= 0 or not c.get("telegram_chat_id"):
            skipped += 1
            continue
        try:
            await telegram_service.send_collection_message(c["id"])
            sent += 1
        except Exception as exc:
            errors.append({"customer": c["name"], "error": str(exc)})
    return {"sent": sent, "skipped": skipped, "errors": errors[:20]}


@app.get("/api/promises")
def promises(status: str = ""):
    return repo.list_promises(status)


@app.patch("/api/promises/{promise_id}")
def patch_promise(promise_id: int, payload: PromisePatch):
    if payload.status not in {"awaiting_date", "promised", "paid", "overdue", "cancelled"}:
        raise HTTPException(400, "وضعیت نامعتبر است")
    if not repo.get_promise(promise_id):
        raise HTTPException(404, "وعده پیدا نشد")
    return repo.update_promise_status(promise_id, payload.status)


@app.get("/api/telegram/status")
def telegram_status():
    return telegram_service.status()


@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "حداکثر حجم فایل 10MB است")
    try:
        (rows, warnings), file_type = parse_file(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"filename": file.filename, "file_type": file_type, "rows": rows[:5000], "total": len(rows), "warnings": warnings}


@app.post("/api/import/commit")
def import_commit(payload: ImportCommit):
    inserted = updated = skipped = 0
    for item in payload.rows:
        if not item.name.strip():
            skipped += 1
            continue
        _, action = repo.upsert_customer(item.name.strip(), item.debt_amount, item.external_id)
        inserted += action == "inserted"
        updated += action == "updated"
    repo.record_import(payload.filename, payload.file_type, len(payload.rows), inserted, updated, skipped)
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# Serve React production build if present.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        target = STATIC_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html")
