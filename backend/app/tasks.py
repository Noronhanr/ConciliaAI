"""Celery: uma tarefa idempotente por página, com persistência de erros."""
from celery import Celery
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.document_assembly import assemble_batch_documents
from app.document_processing import extract_page
from app.models import Batch, Page, SourceFile
from app.storage import download_bytes

celery_app = Celery("concilia", broker=get_settings().redis_url,
                    backend=get_settings().redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1,
                       task_reject_on_worker_lost=True)


@celery_app.task(name="concilia.ping")
def ping() -> str:
    return "pong"


def _refresh_status(session, file_id: int):
    file = session.get(SourceFile, file_id)
    if not file:
        return
    states = list(session.scalars(select(Page.status).where(Page.source_file_id == file_id)))
    if states and all(x in ("ok", "error") for x in states):
        file.status = "error" if "error" in states else "completed"
    session.flush()
    batch = session.get(Batch, file.batch_id)
    file_states = list(session.scalars(select(SourceFile.status).where(SourceFile.batch_id == batch.id)))
    if file_states and all(x in ("completed", "error") for x in file_states):
        batch.status = "error" if "error" in file_states else "completed"
        if batch.status == "completed":
            try:
                assemble_batch_documents(session, batch.id)
            except Exception:
                pass
    elif any(x in ("processing", "completed") for x in file_states):
        batch.status = "processing"



@celery_app.task(name="concilia.process_page", bind=True, max_retries=2)
def process_page(self, page_id: int):
    # Somente a instância que obteve a transição pending -> processing executa OCR.
    with SessionLocal() as db:
        page = db.get(Page, page_id)
        if not page or page.status in ("ok", "error", "processing"):
            return page.status if page else "missing"
        file_id = page.source_file_id
        number = page.page_number
        file = db.get(SourceFile, file_id)
        key, ext = file.object_key, "." + file.filename.rsplit(".", 1)[-1].lower()
        page.status = "processing"
        file.status = "processing"
        db.commit()
    try:
        result = extract_page(download_bytes(key), ext, number)
    except Exception as exc:
        with SessionLocal() as db:
            page = db.get(Page, page_id)
            page.status = "error"
            page.error = str(exc)[:1000]
            _refresh_status(db, page.source_file_id)
            db.commit()
        return "error"
    with SessionLocal() as db:
        page = db.get(Page, page_id)
        page.status = "ok"
        page.ocr_text = result.text
        page.ocr_confidence = result.confidence
        page.ocr_method = result.method
        page.word_boxes = result.boxes
        page.error = None
        _refresh_status(db, page.source_file_id)
        db.commit()
    return "ok"
