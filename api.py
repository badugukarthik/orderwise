import os
import re
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import DEMO_DATE
from ingestion import (
    load_file,
    extract_order_id,
    extract_purchase_date,
    parse_receipt_items,
    make_receipt_item_documents,
    make_policy_documents,
)
from retriever import build_vector_store, get_retriever
from tools import calculate_return_warranty_window, get_order_status
from agent import OrderWarrantyAgent


BASE_DIR = Path(__file__).resolve().parent
POLICY_PATH = BASE_DIR / "data" / "policy.txt"

app = FastAPI(title="Order & Warranty API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: dict[str, dict[str, Any]] = {}


class QuestionRequest(BaseModel):
    session_id: str
    question: str


def _extract_policy_durations(policy_text: str, product: str) -> tuple[int | None, int | None]:
    """Return (return_days, warranty_days) using only explicitly listed policy text."""
    product_lower = product.lower()
    sections = re.split(r"\n\s*(?=[A-Za-z][A-Za-z ]+:\s*$)", policy_text, flags=re.M)

    selected = ""
    for section in sections:
        if product_lower.find("jacket") >= 0 and section.lower().startswith("jackets:"):
            selected = section
        elif product_lower.find("headphone") >= 0 and section.lower().startswith("headphones:"):
            selected = section
        elif product_lower.find("shoe") >= 0 and section.lower().startswith("running shoes:"):
            selected = section

    return_match = re.search(r"Return window:\s*(\d+)\s*days?", selected, re.I)
    warranty_match = re.search(r"Warranty:\s*(\d+)\s*days?", selected, re.I)

    return (
        int(return_match.group(1)) if return_match else None,
        int(warranty_match.group(1)) if warranty_match else None,
    )


def _build_summary(receipt_text: str) -> dict:
    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    order_id = extract_order_id(receipt_text)
    purchase_date = extract_purchase_date(receipt_text)
    items = parse_receipt_items(receipt_text)

    if not order_id or not purchase_date:
        raise ValueError("Could not find Order ID or Purchase Date in the receipt.")
    if not items:
        raise ValueError("No purchased items were found in the receipt.")

    receipt_docs = make_receipt_item_documents(receipt_text)
    policy_docs = make_policy_documents(policy_text)
    vector_store = build_vector_store(receipt_docs, policy_docs)
    retriever = get_retriever(vector_store)

    summary = []
    for item in items:
        return_days, warranty_days = _extract_policy_durations(policy_text, item["product"])
        if return_days is None:
            raise ValueError(f"No explicit return policy found for {item['product']}.")

        calc = calculate_return_warranty_window.invoke({
            "purchase_date": purchase_date,
            "policy_days": return_days,
            "window_type": "return",
        })

        warranty_deadline = None
        if warranty_days is not None:
            warranty_deadline = (
                date.fromisoformat(purchase_date) + timedelta(days=warranty_days)
            ).isoformat()

        summary.append({
            **item,
            **calc,
            "warranty_days": warranty_days,
            "warranty_deadline": warranty_deadline,
        })

    return {
        "order_id": order_id,
        "purchase_date": purchase_date,
        "demo_date": DEMO_DATE.isoformat(),
        "items": summary,
    }, OrderWarrantyAgent(retriever)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/receipt/upload")
async def upload_receipt(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".pdf"}:
        raise HTTPException(status_code=400, detail="Only TXT and PDF receipts are supported.")

    content = await file.read()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        docs = load_file(temp_path)
        receipt_text = "\n".join(doc.page_content for doc in docs)
        summary, agent = _build_summary(receipt_text)

        session_id = uuid.uuid4().hex
        SESSIONS[session_id] = {
            "summary": summary,
            "agent": agent,
        }
        return {"session_id": session_id, "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.get("/api/summary/{session_id}")
def summary(session_id: str):
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Upload the receipt again.")
    return session["summary"]


@app.post("/api/questions")
def question(body: QuestionRequest):
    session = SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Upload the receipt again.")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    return {"answer": session["agent"].answer(body.question)}


@app.get("/api/orders/{order_id}")
def order_status(order_id: str):
    return get_order_status.invoke({"order_id": order_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
