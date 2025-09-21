import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import pytest

# Ensure we load the project's .env (not .env.example) before importing project modules
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / '.env')

# Add the project root to the Python path so `src` can be imported
sys.path.append(str(PROJECT_ROOT))

from src.firebase_sync.firestore_client import FirestoreClient

# Debug: show which credentials are being used
print("[test_firebase_llm] Using .env:", PROJECT_ROOT / '.env')
print("[test_firebase_llm] FIREBASE_PROJECT_ID:", os.getenv('FIREBASE_PROJECT_ID'))
print("[test_firebase_llm] FIREBASE_CLIENT_EMAIL present:", bool(os.getenv('FIREBASE_CLIENT_EMAIL')))


@pytest.fixture(scope="module")
def firestore_client():
    """Fixture to initialize Firestore client using .env credentials."""
    client = FirestoreClient()
    assert client.initialize(), "Failed to initialize Firestore client from .env credentials"
    return client


def test_firestore_retrieval_only(firestore_client):
    """Only verify Firestore retrieval works; do not call LLM here."""
    collection_name = os.getenv("FIREBASE_COLLECTION", "bookings")

    # Try to fetch a small number of documents to validate read permissions
    docs = list(firestore_client.db.collection(collection_name).limit(5).stream())
    print(f"[test_firebase_llm] Retrieved {len(docs)} documents from '{collection_name}'")

    assert docs, "No booking data found in Firestore or permissions are missing"


def test_llm_query_on_firestore_data(firestore_client):
    """Ask the configured LLM a question using RAG context built from Firestore.

    The LLM provider will be set to 'openai' at runtime if an OPENAI_API_KEY is present
    in the loaded `.env`. The import of `answer_question` happens inside the test so
    the provider initializes with the current environment.
    """
    # Ensure provider selection: prefer OpenAI when an API key is present
    if os.getenv("OPENAI_API_KEY"):
        os.environ["LLM_PROVIDER"] = "openai"
    else:
        os.environ["LLM_PROVIDER"] = "local"

    # Import after setting environment so provider initialization picks it up
    from src.llm.llm_skeleton import answer_question

    question = "What cleaning rules are mentioned in the bookings data?"
    result = answer_question(question, k=3)

    print(f"[test_firebase_llm] LLM provider: {result.get('provider')}, model: {result.get('model')}")
    print(f"[test_firebase_llm] Answer preview: {result.get('answer')[:200]}")

    assert isinstance(result.get("answer"), str) and result["answer"].strip(), "LLM returned an empty answer"
