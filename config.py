import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
DEMO_DATE = date.fromisoformat(os.getenv("DEMO_DATE", "2026-09-21"))

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "order_warranty_receipt"
