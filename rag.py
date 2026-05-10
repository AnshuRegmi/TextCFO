"""
RAG module for Tally BI Bot.

Two collections:
  1. ledger_names   — for fuzzy/semantic ledger search
  2. business_rules — for business context injection

Sync from Tally → Vector DB (run periodically)
Query at runtime → inject into LLM prompt
"""

import chromadb
from chromadb.utils import embedding_functions
import os

# ─────────────────────────────────────────────────
#  Setup
# ─────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

# This model runs LOCALLY — no API calls, no cost
# ~90MB download on first run, then cached
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

_client = chromadb.PersistentClient(path=DB_PATH)

def _get_collection(name: str):
    return _client.get_or_create_collection(
        name=name, embedding_function=_ef
    )

# ─────────────────────────────────────────────────
#  SYNC: Tally → Vector DB (run this periodically)
# ─────────────────────────────────────────────────

def sync_ledgers(ledgers: list[dict]):
    """
    Embed all ledger names for semantic search.
    """
    collection = _get_collection("ledger_names")

    # Clear old data (full resync each time)
    existing = collection.count()
    if existing > 0:
        all_ids = collection.get()["ids"]
        if all_ids:
            collection.delete(ids=all_ids)

    if not ledgers:
        print("No ledgers to sync")
        return 0

    ids = []
    documents = []
    metadatas = []

    for i, l in enumerate(ledgers):
        ids.append(f"ledger_{i}")
        documents.append(
            f"{l['name']} — {l['group']} account"
        )
        metadatas.append({
            "name": l["name"],
            "group": l["group"],
            "balance": str(l["balance"]),
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"✅ Embedded {len(ledgers)} ledger names into vector DB")
    return len(ledgers)

def sync_business_rules(rules: list[dict] = None):
    """
    Embed business context that the LLM should know about.
    """
    if rules is None:
        rules = DEFAULT_BUSINESS_RULES

    collection = _get_collection("business_rules")

    # Clear and resync
    existing = collection.count()
    if existing > 0:
        all_ids = collection.get()["ids"]
        if all_ids:
            collection.delete(ids=all_ids)

    collection.upsert(
        ids=[r["id"] for r in rules],
        documents=[r["text"] for r in rules],
    )
    print(f"✅ Embedded {len(rules)} business rules into vector DB")
    return len(rules)

DEFAULT_BUSINESS_RULES = [
    {
        "id": "credit_policy",
        "text": (
            "Standard credit period for customers is 30 days. "
            "Outstanding beyond 45 days is overdue. "
            "Beyond 90 days is bad debt risk and needs immediate follow-up."
        ),
    },
    {
        "id": "margin_targets",
        "text": (
            "Target gross margin is 12-15 percent. "
            "If gross margin drops below 10 percent, it needs attention. "
            "Net profit margin target is 8 percent."
        ),
    },
    {
        "id": "concentration_risk",
        "text": (
            "No single customer should exceed 25 percent of total sales. "
            "Top 3 customers should not exceed 50 percent combined. "
            "This is called concentration risk."
        ),
    },
    {
        "id": "tally_conventions",
        "text": (
            "In Tally, negative balance for Sundry Debtors means "
            "the customer owes us money (debit balance). "
            "Negative balance for Sundry Creditors means "
            "we owe the supplier money. "
            "Financial year runs April to March in India."
        ),
    },
    {
        "id": "payment_terms",
        "text": (
            "Supplier payments should be made within their credit period "
            "to maintain good relationships and avail early payment discounts. "
            "Always verify outstanding amounts before making payments."
        ),
    },
]

# ─────────────────────────────────────────────────
#  QUERY: Search at runtime
# ─────────────────────────────────────────────────

def search_ledgers(query: str, n: int = 5) -> list[dict]:
    """
    Semantic search for ledger names.
    """
    collection = _get_collection("ledger_names")

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n, collection.count()),
    )

    matches = []
    for i in range(len(results["ids"][0])):
        matches.append({
            "name": results["metadatas"][0][i]["name"],
            "group": results["metadatas"][0][i]["group"],
            "balance": results["metadatas"][0][i]["balance"],
            "distance": round(results["distances"][0][i], 3) if results["distances"] else None,
        })
    return matches

def get_relevant_context(query: str, n: int = 2) -> str:
    """
    Retrieve business rules relevant to the user's question.
    """
    collection = _get_collection("business_rules")

    if collection.count() == 0:
        return ""

    results = collection.query(
        query_texts=[query],
        n_results=min(n, collection.count()),
    )

    if not results["documents"][0]:
        return ""

    return "\n\n".join(results["documents"][0])

# CLI Test Section
if __name__ == "__main__":
    from tally_mcp import _parse_ledgers, tally_collection

    print("=" * 50)
    print("  RAG Sync + Test")
    print("=" * 50)

    print("\n1. Syncing ledgers from Tally...")
    raw = tally_collection("Ledger")
    ledgers = _parse_ledgers(raw)
    sync_ledgers(ledgers)

    print("\n2. Syncing business rules...")
    sync_business_rules()

    print("\n" + "=" * 50)
    print("  Testing Semantic Search")
    print("=" * 50)

    test_queries = ["cash", "bank", "rent expenses", "debtor", "supplier"]
    for q in test_queries:
        matches = search_ledgers(q, n=3)
        print(f"\n  Search: '{q}'")
        for m in matches:
            print(f"    → {m['name']} ({m['group']}) [distance: {m['distance']}]")

    print("\n" + "=" * 50)
    print("  Testing Context Retrieval")
    print("=" * 50)

    context_queries = [
        "is this payment overdue?",
        "what margin should we target?",
        "too much sales from one customer",
    ]
    for q in context_queries:
        ctx = get_relevant_context(q)
        print(f"\n  Query: '{q}'")
        print(f"  Context: {ctx[:150]}...")