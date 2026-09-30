import os
import re
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ingestion import (
    load_file,
    extract_order_id,
    extract_purchase_date,
    parse_receipt_items,
)
from config import DEMO_DATE

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"
POLICY_PATH = DATA_DIR / "policy.txt"

app = FastAPI(
    title="OrderWise — Order & Warranty Assistant",
    version="1.0.0",
    description="Public web app for receipt summaries, deadlines, policy questions, and order lookup.",
)

# Same-origin is used in normal deployment. These settings also make local testing easy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

SESSIONS: dict[str, dict[str, Any]] = {}


class QuestionRequest(BaseModel):
    session_id: str
    question: str


def reference_date() -> date:
    """Use live server date for a public site when LIVE_DEADLINES=true.
    Otherwise preserve the demo date from the user's existing backend."""
    if os.getenv("LIVE_DEADLINES", "false").lower() == "true":
        return date.today()
    return DEMO_DATE


def parse_policy_sections(policy_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(
        r"(?ms)^\s*([A-Za-z][A-Za-z ]+):\s*$\n(.*?)(?=^\s*[A-Za-z][A-Za-z ]+:\s*$|\Z)",
        policy_text,
    ))
    for match in matches:
        sections[match.group(1).strip().lower()] = match.group(0).strip()
    return sections


def policy_for_product(product: str, policy_text: str) -> dict[str, Any]:
    sections = parse_policy_sections(policy_text)
    p = product.lower()

    if "headphone" in p:
        key = "headphones"
    elif "jacket" in p:
        key = "jackets"
    elif "shoe" in p:
        key = "running shoes"
    else:
        key = None

    section = sections.get(key, "") if key else ""

    ret = re.search(r"Return window:\s*(\d+)\s*days?", section, re.I)
    warranty = re.search(r"Warranty:\s*(\d+)\s*days?", section, re.I)

    return {
        "section": section,
        "return_days": int(ret.group(1)) if ret else None,
        "warranty_days": int(warranty.group(1)) if warranty else None,
    }


def calculate_window(purchase_date: str, days: int) -> dict[str, Any]:
    purchase = date.fromisoformat(purchase_date)
    deadline = purchase + timedelta(days=days)
    as_of = reference_date()
    remaining = (deadline - as_of).days

    return {
        "deadline": deadline.isoformat(),
        "days_remaining": remaining,
        "expiring_soon": 0 <= remaining < 7,
        "expired": remaining < 0,
    }


def build_summary(receipt_text: str) -> dict[str, Any]:
    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    order_id = extract_order_id(receipt_text)
    purchase_date = extract_purchase_date(receipt_text)
    items = parse_receipt_items(receipt_text)

    if not order_id or not purchase_date:
        raise ValueError(
            "Could not find both Order ID and Purchase Date. "
            "Expected labels like 'Order ID:' and 'Purchase Date: YYYY-MM-DD'."
        )
    if not items:
        raise ValueError("No purchased items were detected in this receipt.")

    result_items = []
    for item in items:
        policy = policy_for_product(item["product"], policy_text)
        if policy["return_days"] is None:
            raise ValueError(
                f"No explicit return window is listed in policy.txt for {item['product']}."
            )

        ret_calc = calculate_window(purchase_date, policy["return_days"])
        warranty_deadline = None
        warranty_remaining = None
        warranty_expiring_soon = False
        warranty_expired = False

        if policy["warranty_days"] is not None:
            warranty_calc = calculate_window(purchase_date, policy["warranty_days"])
            warranty_deadline = warranty_calc["deadline"]
            warranty_remaining = warranty_calc["days_remaining"]
            warranty_expiring_soon = warranty_calc["expiring_soon"]
            warranty_expired = warranty_calc["expired"]

        result_items.append({
            **item,
            "policy_days": policy["return_days"],
            "deadline": ret_calc["deadline"],
            "days_remaining": ret_calc["days_remaining"],
            "expiring_soon": ret_calc["expiring_soon"],
            "expired": ret_calc["expired"],
            "warranty_days": policy["warranty_days"],
            "warranty_deadline": warranty_deadline,
            "warranty_days_remaining": warranty_remaining,
            "warranty_expiring_soon": warranty_expiring_soon,
            "warranty_expired": warranty_expired,
        })

    return {
        "order_id": order_id,
        "purchase_date": purchase_date,
        "as_of_date": reference_date().isoformat(),
        "live_deadlines": os.getenv("LIVE_DEADLINES", "false").lower() == "true",
        "items": result_items,
        "total": round(sum(i["price"] for i in result_items), 2),
    }


def order_lookup(order_id: str) -> dict[str, Any]:
    path = DATA_DIR / "orders.csv"
    if not path.exists():
        return {"found": False, "message": "Order database is unavailable."}

    orders = pd.read_csv(path, dtype=str)
    order_id = order_id.strip().upper()
    matches = orders[orders["order_id"].str.strip().str.upper() == order_id]

    if matches.empty:
        return {
            "found": False,
            "order_id": order_id,
            "message": "Order not found in the available order database.",
        }

    row = matches.iloc[0]
    return {
        "found": True,
        "order_id": row["order_id"],
        "status": row["status"],
        "expected_delivery": row["expected_delivery"],
    }


def deterministic_answer(summary: dict[str, Any], question: str) -> str:
    """Policy-grounded fallback that requires no external LLM service."""
    q = question.lower().strip()
    items = summary["items"]

    # Order questions are handled directly from the mock database.
    match = re.search(r"\b(ord\d+)\b", q, re.I)
    if match and any(word in q for word in ["status", "delivery", "delivered", "shipped", "processing"]):
        result = order_lookup(match.group(1))
        if not result["found"]:
            return result["message"]
        return (
            f"Order {result['order_id']} is {result['status']}. "
            f"Expected delivery: {result['expected_delivery']}."
        )

    chosen = None
    for item in items:
        if item["product"].lower() in q:
            chosen = item
            break
        for token in item["product"].lower().split():
            if len(token) >= 5 and token in q:
                chosen = item
                break
        if chosen:
            break

    if any(word in q for word in ["which products", "what did i buy", "purchased items", "bought"]):
        names = ", ".join(item["product"] for item in items)
        return f"Your receipt contains: {names}."

    if "order id" in q:
        return f"Your order ID is {summary['order_id']}."

    if "purchase date" in q or "bought on" in q:
        return f"The purchase date on the receipt is {summary['purchase_date']}."

    if chosen:
        if any(word in q for word in ["price", "cost", "how much"]):
            return f"{chosen['product']} is listed at INR {chosen['price']:.2f}."

        if any(word in q for word in ["warranty", "guarantee"]):
            if chosen["warranty_days"] is None:
                return (
                    f"The policy does not list a warranty period for {chosen['product']}. "
                    "Only explicitly listed warranty periods are used."
                )
            return (
                f"The warranty for {chosen['product']} is {chosen['warranty_days']} days "
                f"from the purchase date, with a deadline of {chosen['warranty_deadline']}."
            )

        if any(word in q for word in ["return", "refund", "send back"]):
            return (
                f"The return window for {chosen['product']} is {chosen['policy_days']} days "
                f"from the purchase date. The return deadline is {chosen['deadline']}."
            )

        if any(word in q for word in ["deadline", "expires", "remaining", "left"]):
            return (
                f"{chosen['product']} has {chosen['days_remaining']} day(s) remaining "
                f"for return as of {summary['as_of_date']}. "
                f"The deadline is {chosen['deadline']}."
            )

    # General policy summary for broad questions.
    lines = []
    for item in items:
        warranty = (
            f" Warranty: {item['warranty_days']} days."
            if item["warranty_days"] is not None
            else ""
        )
        lines.append(
            f"{item['product']}: {item['policy_days']}-day return window "
            f"(deadline {item['deadline']}).{warranty}"
        )
    return (
        "Here are the policy details I can verify from your receipt and store policy:\n"
        + "\n".join(lines)
    )


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/favicon.svg")
def favicon():
    path = FRONTEND_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "OrderWise",
        "as_of_date": reference_date().isoformat(),
        "live_deadlines": os.getenv("LIVE_DEADLINES", "false").lower() == "true",
    }


@app.post("/api/receipt/upload")
async def upload_receipt(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="Please upload a PDF or TXT receipt.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Receipt file is too large. Maximum size is 10 MB.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        raw_docs = load_file(temp_path)
        receipt_text = "\n".join(doc.page_content for doc in raw_docs)
        summary = build_summary(receipt_text)

        session_id = uuid.uuid4().hex
        SESSIONS[session_id] = {
            "summary": summary,
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
        raise HTTPException(status_code=404, detail="This session has expired. Please upload the receipt again.")
    return session["summary"]


@app.post("/api/questions")
def question(body: QuestionRequest):
    session = SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="This session has expired. Please upload the receipt again.")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Please enter a question.")

    return {
        "answer": deterministic_answer(session["summary"], body.question.strip()),
        "source": "receipt + store policy",
    }


@app.get("/api/orders/{order_id}")
def order_status(order_id: str):
    return order_lookup(order_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_public:app",
        host="127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
