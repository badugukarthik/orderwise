import re
from typing import Dict, List

from langchain_ollama import ChatOllama
from langchain_core.documents import Document

from config import OLLAMA_MODEL
from tools import get_order_status


class OrderWarrantyAgent:
    """Small, reliable agent wrapper around retrieval, tools, and ChatOllama."""

    def __init__(self, retriever):
        self.retriever = retriever
        self.llm = ChatOllama(
            model=OLLAMA_MODEL,
            temperature=0,
        )

    def retrieve(self, query: str) -> List[Document]:
        return self.retriever.invoke(query)

    def answer(self, query: str) -> str:
        # Order-status questions go directly to the database tool.
        order_match = re.search(r"\b(ORD\d+)\b", query, re.I)
        status_words = ["status", "delivery", "delivered", "shipped", "processing"]

        if order_match and any(word in query.lower() for word in status_words):
            result = get_order_status.invoke(
                {"order_id": order_match.group(1).upper()}
            )

            if not result.get("found"):
                return f"❌ {result.get('message', 'Order not found.')}"

            return (
                f"📦 Order {result['order_id']} is **{result['status']}**. "
                f"Expected delivery: **{result['expected_delivery']}**."
            )

        docs = self.retrieve(query)

        if not docs:
            return "I couldn't find that information in the uploaded receipt or store policy."

        context = "\n\n---\n\n".join(doc.page_content for doc in docs)

        prompt = f"""
You are an Order & Warranty Agent.

Answer the customer's question using ONLY the context below.
Do not invent products, dates, prices, return periods, warranty periods,
or policy terms.

If the answer is not in the context, say:
"I couldn't find that information in the uploaded receipt or store policy."

Context:
{context}

Customer question:
{query}
"""

        response = self.llm.invoke(prompt)
        return response.content
