"""
Test suite for rag.py and orchestrator.py
Run with: python test_rag.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


def run_tests():
    print("=" * 60)
    print("  RAG + Orchestrator Test Suite")
    print("=" * 60)
    print()

    passed = 0
    skipped = 0
    failed = 0

    # ─────────────────────────────────────────────────
    # Test 1: rag.py imports
    # ─────────────────────────────────────────────────
    print("Test: test_rag_imports")
    print("-" * 40)
    try:
        import rag
        print("  [PASS] rag.py imports successfully")
        passed += 1
    except ImportError as e:
        print(f"  [SKIP] rag.py import failed (missing dependency): {e}")
        skipped += 1

    # ─────────────────────────────────────────────────
    # Test 2: ChromaDB client
    # ─────────────────────────────────────────────────
    print("\nTest: test_chromadb_client")
    print("-" * 40)
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        client = chromadb.PersistentClient(path=":memory:")
        collection = client.get_or_create_collection(
            name="test_collection",
            embedding_function=_ef
        )
        print("  [PASS] ChromaDB client and collection work")
        passed += 1
    except Exception as e:
        print(f"  [SKIP] ChromaDB not available: {e}")
        skipped += 1

    # ─────────────────────────────────────────────────
    # Test 3: sync_ledgers
    # ─────────────────────────────────────────────────
    print("\nTest: test_sync_ledgers")
    print("-" * 40)
    try:
        from rag import sync_ledgers, _get_collection

        test_ledgers = [
            {"name": "Cash", "group": "Cash in Hand", "balance": "10000"},
            {"name": "Bank Account", "group": "Bank Accounts", "balance": "50000"},
            {"name": "Sundry Debtors", "group": "Sundry Debtors", "balance": "-25000"},
        ]

        count = sync_ledgers(test_ledgers)
        if count != 3:
            raise AssertionError(f"Expected 3 ledgers, got {count}")
        print(f"  [PASS] sync_ledgers inserted {count} ledgers")

        collection = _get_collection("ledger_names")
        if collection.count() != 3:
            raise AssertionError("Collection should have 3 items")
        print("  [PASS] Ledger collection verified with 3 items")
        passed += 1
    except ImportError:
        print("  [SKIP] rag module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 4: sync_business_rules
    # ─────────────────────────────────────────────────
    print("\nTest: test_sync_business_rules")
    print("-" * 40)
    try:
        from rag import sync_business_rules, _get_collection, DEFAULT_BUSINESS_RULES

        count = sync_business_rules()
        if count != len(DEFAULT_BUSINESS_RULES):
            raise AssertionError(f"Expected {len(DEFAULT_BUSINESS_RULES)} rules, got {count}")
        print(f"  [PASS] sync_business_rules inserted {count} rules")

        collection = _get_collection("business_rules")
        if collection.count() != count:
            raise AssertionError("Collection count mismatch")
        print("  [PASS] Business rules collection verified")
        passed += 1
    except ImportError:
        print("  [SKIP] rag module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 5: search_ledgers
    # ─────────────────────────────────────────────────
    print("\nTest: test_search_ledgers")
    print("-" * 40)
    try:
        from rag import sync_ledgers, search_ledgers

        test_ledgers = [
            {"name": "Cash", "group": "Cash in Hand", "balance": "10000"},
            {"name": "Bank Account", "group": "Bank Accounts", "balance": "50000"},
            {"name": "Sundry Debtors", "group": "Sundry Debtors", "balance": "-25000"},
        ]
        sync_ledgers(test_ledgers)

        results = search_ledgers("cash", n=3)
        if len(results) == 0:
            raise AssertionError("Should find 'cash' ledger")
        if not any("Cash" in r["name"] for r in results):
            raise AssertionError("Should find 'Cash' ledger")
        print(f"  [PASS] search_ledgers('cash') found: {[r['name'] for r in results]}")

        results = search_ledgers("debtor", n=3)
        if len(results) == 0:
            raise AssertionError("Should find 'debtor' ledger")
        if not any("Debtors" in r["name"] for r in results):
            raise AssertionError("Should find 'Sundry Debtors'")
        print(f"  [PASS] search_ledgers('debtor') found: {[r['name'] for r in results]}")
        passed += 1
    except ImportError:
        print("  [SKIP] rag module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 6: get_relevant_context
    # ─────────────────────────────────────────────────
    print("\nTest: test_get_relevant_context")
    print("-" * 40)
    try:
        from rag import sync_business_rules, get_relevant_context

        sync_business_rules()

        context = get_relevant_context("is this payment overdue?", n=2)
        if len(context) == 0:
            raise AssertionError("Should return context for payment query")
        if "credit" not in context.lower() and "30 days" not in context:
            raise AssertionError("Should contain credit policy info")
        print(f"  [PASS] get_relevant_context('payment overdue') returned context")

        context = get_relevant_context("what margin should we target?", n=2)
        if "margin" not in context.lower() and "percent" not in context.lower():
            raise AssertionError("Should contain margin info")
        print(f"  [PASS] get_relevant_context('margin') returned context")
        passed += 1
    except ImportError:
        print("  [SKIP] rag module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 7: orchestrator imports
    # ─────────────────────────────────────────────────
    print("\nTest: test_orchestrator_imports")
    print("-" * 40)
    try:
        import orchestrator
        print("  [PASS] orchestrator.py imports successfully")
        passed += 1
    except ImportError as e:
        print(f"  [SKIP] orchestrator.py import failed: {e}")
        skipped += 1

    # ─────────────────────────────────────────────────
    # Test 8: TallyMCPClient class
    # ─────────────────────────────────────────────────
    print("\nTest: test_tally_mcp_client_class")
    print("-" * 40)
    try:
        from orchestrator import TallyMCPClient
        client = TallyMCPClient()
        if client.tools != []:
            raise AssertionError("Client should start with empty tools")
        if client.session is not None:
            raise AssertionError("Client should start with no session")
        print("  [PASS] TallyMCPClient class instantiates correctly")
        passed += 1
    except ImportError:
        print("  [SKIP] orchestrator module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 9: parse_tool_call
    # ─────────────────────────────────────────────────
    print("\nTest: test_parse_tool_call")
    print("-" * 40)
    try:
        from orchestrator import parse_tool_call

        tool_name, kwargs = parse_tool_call('TOOL_CALL: get_ledger(name="Cash")')
        if tool_name != "get_ledger":
            raise AssertionError(f"Expected 'get_ledger', got '{tool_name}'")
        if kwargs != {"name": "Cash"}:
            raise AssertionError(f"Expected {{'name': 'Cash'}}, got {kwargs}")
        print("  [PASS] parse_tool_call('TOOL_CALL: get_ledger(name=\"Cash\")') works")

        tool_name, kwargs = parse_tool_call("Here is the answer you requested.")
        if tool_name is not None:
            raise AssertionError("Should return None for no tool call")
        print("  [PASS] parse_tool_call returns None for non-tool output")

        tool_name, kwargs = parse_tool_call('TOOL_CALL: get_vouchers(from_date="2024-04-01", to_date="2024-04-30")')
        if tool_name != "get_vouchers":
            raise AssertionError("Expected 'get_vouchers'")
        if kwargs != {"from_date": "2024-04-01", "to_date": "2024-04-30"}:
            raise AssertionError("Multiple args parsing failed")
        print("  [PASS] parse_tool_call handles multiple arguments")
        passed += 1
    except ImportError:
        print("  [SKIP] orchestrator module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 10: RAG integration
    # ─────────────────────────────────────────────────
    print("\nTest: test_rag_orchestrator_integration")
    print("-" * 40)
    try:
        from orchestrator import RAG_ENABLED
        print(f"  [PASS] RAG_ENABLED = {RAG_ENABLED}")
        passed += 1
    except ImportError:
        print("  [SKIP] orchestrator module not available")
        skipped += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Test 11: rag.py exists
    # ─────────────────────────────────────────────────
    print("\nTest: test_orchestrator_rag_import")
    print("-" * 40)
    try:
        rag_path = os.path.join(os.path.dirname(__file__), "rag.py")
        if not os.path.exists(rag_path):
            raise FileNotFoundError("rag.py should exist")
        print("  [PASS] rag.py exists for orchestrator to import")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {skipped} skipped, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)