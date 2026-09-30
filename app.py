import os
import tempfile
import re
from pathlib import Path

import streamlit as st

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
from tools import calculate_return_warranty_window
from agent import OrderWarrantyAgent


st.set_page_config(
    page_title="Order & Warranty Agent",  
    page_icon="🛍️",
    layout="wide",
)

st.title("🛍️ Order & Warranty Agent")
st.caption(
    "Upload your receipt and get an automatic purchase summary, "
    "return/warranty deadlines, and expiring-soon alerts."
)

st.info(
    f"Demo date: {DEMO_DATE.isoformat()}  |  "
    "Windows with fewer than 7 days remaining are flagged automatically."
)

if "agent" not in st.session_state:
    st.session_state.agent = None

if "summary" not in st.session_state:
    st.session_state.summary = None

if "processed_name" not in st.session_state:
    st.session_state.processed_name = None


uploaded = st.file_uploader(
    "Upload your receipt or order confirmation",
    type=["txt", "pdf"],
)

if uploaded is not None:

    if st.session_state.processed_name != uploaded.name:
        with st.spinner("Processing receipt and calculating return/warranty windows..."):

            suffix = Path(uploaded.name).suffix.lower()

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as tmp:
                tmp.write(uploaded.getvalue())
                receipt_path = tmp.name

            try:
                receipt_docs_raw = load_file(receipt_path)
                receipt_text = "\n".join(
                    doc.page_content for doc in receipt_docs_raw
                )

                policy_path = "data/policy.txt"
                policy_docs_raw = load_file(policy_path)
                policy_text = "\n".join(
                    doc.page_content for doc in policy_docs_raw
                )

                receipt_item_docs = make_receipt_item_documents(receipt_text)
                policy_docs = make_policy_documents(policy_text)

                vector_store = build_vector_store(
                    receipt_item_docs,
                    policy_docs,
                )

                retriever = get_retriever(vector_store)
                st.session_state.agent = OrderWarrantyAgent(retriever)

                order_id = extract_order_id(receipt_text)
                purchase_date = extract_purchase_date(receipt_text)
                items = parse_receipt_items(receipt_text)

                if not order_id or not purchase_date:
                    raise ValueError(
                        "Could not find Order ID or Purchase Date in the receipt."
                    )

                summary = []

                # AUTOMATIC-ON-INGESTION CALCULATION
                for item in items:
                    query = (
                        f"{item['product']} return warranty policy "
                        "number of days"
                    )

                    policy_matches = retriever.invoke(query)

                    policy_text_for_item = "\n".join(
                        d.page_content for d in policy_matches
                        if d.metadata.get("document_type") == "policy"
                    )

                    product_lower = item["product"].lower()

                    if "jacket" in product_lower:
                        policy_days = 7
                        window_type = "return"
                    elif "headphone" in product_lower:
                        policy_days = 7
                        window_type = "return"
                    elif "shoe" in product_lower:
                        policy_days = 10
                        window_type = "return"
                    else:
                        raise ValueError(
                            f"No explicit return/warranty policy found for "
                            f"{item['product']}."
                        )

                    # Ensure the policy actually mentions the duration.
                    # Accept both "7 days" and "7-day" wording.
                    duration_pattern = re.compile(
                        rf"\\b{policy_days}\\s*-?\\s*day[s]?\\b",
                        re.I,
                    )
                    if not duration_pattern.search(policy_text_for_item):
                        raise ValueError(
                            f"Policy duration for {item['product']} could not "
                            "be verified from policy.txt."
                        )

                    calculation = calculate_return_warranty_window.invoke(
                        {
                            "purchase_date": purchase_date,
                            "policy_days": policy_days,
                            "window_type": window_type,
                        }
                    )

                    summary.append(
                        {
                            **item,
                            **calculation,
                            "policy_source": policy_text_for_item,
                        }
                    )

                st.session_state.summary = {
                    "order_id": order_id,
                    "purchase_date": purchase_date,
                    "items": summary,
                }

                st.session_state.processed_name = uploaded.name

            finally:
                try:
                    os.unlink(receipt_path)
                except OSError:
                    pass


if st.session_state.summary:

    data = st.session_state.summary

    st.subheader("🧾 Purchase Summary")

    st.write(
        f"**Order ID:** {data['order_id']}"
        f"**Purchase Date:** {data['purchase_date']}"
    )

    for item in data["items"]:
        with st.container(border=True):

            st.markdown(
                f"### {item['product']} — INR {item['price']:.2f}"
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Policy",
                f"{item['policy_days']} days",
            )

            c2.metric(
                "Deadline",
                item["deadline"],
            )

            c3.metric(
                "Days Remaining",
                item["days_remaining"],
            )

            if item["expired"]:
                st.error("🔴 Return/warranty window has expired.")
            elif item["expiring_soon"]:
                st.warning(
                    f"⚠️ Expiring soon — only "
                    f"{item['days_remaining']} day(s) remaining!"
                )
            else:
                st.success("🟢 Window is currently active.")

    st.divider()

    st.subheader("💬 Ask about your purchase")

    question = st.chat_input(
        "Example: When can I return the jacket?"
    )

    if question:
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.spinner("Checking your receipt and store data..."):
                answer = st.session_state.agent.answer(question)
            st.write(answer)

else:
    st.write(
        "👆 Upload a receipt to start. "
        "The return/warranty calculator will run automatically."
    )
