#!/usr/bin/env python3
"""
Client isolation integration test for the Callwen API.

Verifies that documents, RAG responses, action items, timelines, and chat
histories are fully isolated between different clients owned by the same user.

Authentication — no manual token needed. This script uses TEST_MODE:
  1. It reads CLERK_SECRET_KEY from backend/.env.local automatically.
  2. It sends that key as the Bearer token.
  3. When TEST_MODE=true in .env.local, the backend accepts this and returns a
     fixed test user, bypassing Clerk JWT verification entirely.

Setup (one-time):
  Add TEST_MODE=true to backend/.env.local, then start the backend normally.

Usage (direct):
    python backend/tests/test_client_isolation.py

Usage (pytest):
    pytest backend/tests/test_client_isolation.py -v -s
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"
MAX_WAIT_SECONDS = 120
POLL_INTERVAL = 3

# Unique opaque strings embedded in each client's document.
# If RAG leaks across clients, these will appear in the wrong chat answers.
CLIENT_A_MARKER = "ISOLATION_ALPHA_XQ7Z9"
CLIENT_B_MARKER = "ISOLATION_BETA_WR4K2"

# ─── Result tracker ───────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []  # (label, passed, detail)


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    line = f"  [{status}] {label}"
    if detail and not condition:
        line += f"\n         → {detail}"
    print(line)
    _results.append((label, condition, detail))
    return condition


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env.local parser — handles KEY=value and KEY="value", skips comments."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        result[key] = val
    return result


def get_headers() -> dict[str, str]:
    """
    Returns auth headers for the test HTTP client.

    Priority:
    1. CLERK_TEST_TOKEN env var — for manual runs with a short-lived JWT.
    2. TEST_MODE bypass — reads CLERK_SECRET_KEY from backend/.env.local and sends
       it as the Bearer token. Requires TEST_MODE=true in backend/.env.local.
    """
    # 1. Explicit override still works (backwards compat)
    explicit = os.environ.get("CLERK_TEST_TOKEN", "").strip()
    if explicit:
        return {"Authorization": f"Bearer {explicit}"}

    # 2. Auto-detect from .env.local
    env_file = Path(__file__).parent.parent / ".env.local"
    env_vars = _parse_dotenv(env_file)

    test_mode = env_vars.get("TEST_MODE", "").lower() in ("1", "true", "yes")
    secret_key = env_vars.get("CLERK_SECRET_KEY", "").strip()

    if not test_mode:
        print("ERROR: TEST_MODE is not enabled.")
        print(f"       Add TEST_MODE=true to {env_file}")
        print("       Then restart the backend and re-run this script.")
        print()
        print("       Alternatively, set CLERK_TEST_TOKEN=<jwt> for a manual run.")
        sys.exit(1)

    if not secret_key:
        print(f"ERROR: CLERK_SECRET_KEY not found in {env_file}")
        sys.exit(1)

    return {"Authorization": f"Bearer {secret_key}"}


def wait_for_processing(client: httpx.Client, client_id: str, label: str) -> bool:
    """Poll RAG status until processed > 0 and pending == 0, or until timeout."""
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        r = client.get(f"/api/clients/{client_id}/rag/status")
        if r.status_code == 200:
            s = r.json()
            processed = s.get("processed", 0)
            pending = s.get("pending", 0)
            errors = s.get("errors", 0)
            print(f"    {label}: processed={processed} pending={pending} errors={errors}")
            if processed > 0 and pending == 0:
                return True
            if errors > 0 and pending == 0:
                return False
        time.sleep(POLL_INTERVAL)
    return False


def doc_content(client_name: str, subject: str, body: str, marker: str) -> bytes:
    return (
        f"ADVISORY DOCUMENT\n\n"
        f"Client:  {client_name}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n\n"
        f"Reference Code: {marker}\n"
        f"This document belongs exclusively to {client_name} "
        f"and must not surface in queries for any other client.\n"
    ).encode()


# ─── Main test routine ────────────────────────────────────────────────────────

def run_tests() -> bool:
    headers = get_headers()
    http = httpx.Client(base_url=BASE_URL, headers=headers, timeout=60)

    client_a_id: str | None = None
    client_b_id: str | None = None

    try:
        # ══ 1. Resolve client types ══════════════════════════════════════════
        print("\n── 1. Resolving client types ──")
        r = http.get("/api/client-types")
        check("GET /api/client-types → 200", r.status_code == 200, r.text[:200])

        type_map: dict[str, Any] = {
            t["name"]: t["id"] for t in r.json().get("types", [])
        }
        tax_type_id = type_map.get("Tax Planning")
        fin_type_id = type_map.get("Financial Advisory")
        check("'Tax Planning' client type exists", tax_type_id is not None)
        check("'Financial Advisory' client type exists", fin_type_id is not None)

        # ══ 2. Create two test clients ═══════════════════════════════════════
        print("\n── 2. Creating test clients ──")
        r = http.post("/api/clients", json={
            "name": "Isolation Test — Client A (Tax)",
            "client_type_id": tax_type_id,
            "notes": "Automated isolation test — safe to delete",
        })
        check(
            "Create Client A → 200/201",
            r.status_code in (200, 201),
            r.text[:200],
        )
        client_a_id = r.json()["id"]
        print(f"    Client A id: {client_a_id}")

        r = http.post("/api/clients", json={
            "name": "Isolation Test — Client B (Financial)",
            "client_type_id": fin_type_id,
            "notes": "Automated isolation test — safe to delete",
        })
        check(
            "Create Client B → 200/201",
            r.status_code in (200, 201),
            r.text[:200],
        )
        client_b_id = r.json()["id"]
        print(f"    Client B id: {client_b_id}")

        # ══ 3. Upload unique documents ════════════════════════════════════════
        print("\n── 3. Uploading documents ──")
        doc_a = doc_content(
            client_name="Isolation Test Client A",
            subject="Q4 Tax Optimization Strategy",
            body=(
                "Key recommendations:\n"
                "1. Maximize charitable contributions up to 60% of AGI.\n"
                "2. Harvest capital losses to offset realized gains.\n"
                "3. Contribute maximum to SEP-IRA before fiscal year-end.\n"
                "4. Review Section 179 depreciation elections.\n"
            ),
            marker=CLIENT_A_MARKER,
        )
        doc_b = doc_content(
            client_name="Isolation Test Client B",
            subject="Q4 Portfolio Rebalancing Review",
            body=(
                "Key recommendations:\n"
                "1. Rebalance equity/fixed-income to 60/40 split.\n"
                "2. Increase international equity exposure by 5 percentage points.\n"
                "3. Reduce single-stock concentration risk across the portfolio.\n"
                "4. Review bond duration given the current rate environment.\n"
            ),
            marker=CLIENT_B_MARKER,
        )

        r = http.post(
            f"/api/clients/{client_a_id}/documents",
            files={"file": ("tax_memo_client_a.txt", doc_a, "text/plain")},
        )
        check(
            "Upload document to Client A → 200/201",
            r.status_code in (200, 201),
            r.text[:200],
        )

        r = http.post(
            f"/api/clients/{client_b_id}/documents",
            files={"file": ("financial_report_client_b.txt", doc_b, "text/plain")},
        )
        check(
            "Upload document to Client B → 200/201",
            r.status_code in (200, 201),
            r.text[:200],
        )

        # ══ 4. Trigger RAG processing ══════════════════════════════════════════
        print("\n── 4. Triggering RAG processing ──")
        r = http.post(f"/api/clients/{client_a_id}/rag/process")
        check("Queue RAG process for Client A → 200", r.status_code == 200, r.text[:200])

        r = http.post(f"/api/clients/{client_b_id}/rag/process")
        check("Queue RAG process for Client B → 200", r.status_code == 200, r.text[:200])

        # ══ 5. Wait for processing ════════════════════════════════════════════
        print(f"\n── 5. Waiting for processing (up to {MAX_WAIT_SECONDS}s each) ──")
        a_ready = wait_for_processing(http, client_a_id, "Client A")
        check("Client A document processed without errors", a_ready)

        b_ready = wait_for_processing(http, client_b_id, "Client B")
        check("Client B document processed without errors", b_ready)

        if not (a_ready and b_ready):
            print("\n  WARNING: Processing did not complete — RAG tests may give false results.")

        # ══ 6. Document list isolation ════════════════════════════════════════
        print("\n── 6. Document list isolation ──")
        r_a = http.get(f"/api/clients/{client_a_id}/documents")
        r_b = http.get(f"/api/clients/{client_b_id}/documents")

        filenames_a = {d["filename"] for d in r_a.json().get("items", [])}
        filenames_b = {d["filename"] for d in r_b.json().get("items", [])}

        check(
            "Client A doc list contains tax_memo_client_a.txt",
            "tax_memo_client_a.txt" in filenames_a,
            f"filenames_a={filenames_a}",
        )
        check(
            "Client A doc list does NOT contain financial_report_client_b.txt",
            "financial_report_client_b.txt" not in filenames_a,
            f"filenames_a={filenames_a}",
        )
        check(
            "Client B doc list contains financial_report_client_b.txt",
            "financial_report_client_b.txt" in filenames_b,
            f"filenames_b={filenames_b}",
        )
        check(
            "Client B doc list does NOT contain tax_memo_client_a.txt",
            "tax_memo_client_a.txt" not in filenames_b,
            f"filenames_b={filenames_b}",
        )

        # ══ 7. RAG / chat isolation ═══════════════════════════════════════════
        print("\n── 7. RAG chat isolation ──")

        # Client A: ask about its own marker
        r = http.post(
            f"/api/clients/{client_a_id}/rag/chat",
            json={"question": "What is the unique reference code in this document?"},
        )
        check("RAG chat for Client A → 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            resp = r.json()
            answer_a = resp.get("answer", "")
            sources_a = [s["filename"] for s in resp.get("sources", [])]

            check(
                "Client A answer references its own marker or document",
                CLIENT_A_MARKER in answer_a or "tax_memo_client_a.txt" in sources_a,
                f"answer={answer_a[:300]}  sources={sources_a}",
            )
            check(
                "Client A answer does NOT contain Client B's marker",
                CLIENT_B_MARKER not in answer_a,
                f"Found {CLIENT_B_MARKER!r} in answer: {answer_a[:300]}",
            )
            check(
                "Client B's document not in Client A's RAG sources",
                "financial_report_client_b.txt" not in sources_a,
                f"sources_a={sources_a}",
            )

        # Client B: ask about its own marker
        r = http.post(
            f"/api/clients/{client_b_id}/rag/chat",
            json={"question": "What is the unique reference code in this document?"},
        )
        check("RAG chat for Client B → 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            resp = r.json()
            answer_b = resp.get("answer", "")
            sources_b = [s["filename"] for s in resp.get("sources", [])]

            check(
                "Client B answer references its own marker or document",
                CLIENT_B_MARKER in answer_b or "financial_report_client_b.txt" in sources_b,
                f"answer={answer_b[:300]}  sources={sources_b}",
            )
            check(
                "Client B answer does NOT contain Client A's marker",
                CLIENT_A_MARKER not in answer_b,
                f"Found {CLIENT_A_MARKER!r} in answer: {answer_b[:300]}",
            )
            check(
                "Client A's document not in Client B's RAG sources",
                "tax_memo_client_a.txt" not in sources_b,
                f"sources_b={sources_b}",
            )

        # Cross-query: ask Client A about Client B's marker directly
        r = http.post(
            f"/api/clients/{client_a_id}/rag/chat",
            json={"question": f"What is {CLIENT_B_MARKER}?"},
        )
        if r.status_code == 200:
            cross = r.json()
            cross_answer = cross.get("answer", "")
            cross_sources = [s["filename"] for s in cross.get("sources", [])]
            check(
                "Client A cannot surface Client B's marker via direct query",
                CLIENT_B_MARKER not in cross_answer
                and "financial_report_client_b.txt" not in cross_sources,
                f"answer={cross_answer[:300]}  sources={cross_sources}",
            )

        # ══ 8. Action item isolation ══════════════════════════════════════════
        print("\n── 8. Action item isolation ──")
        r_a = http.get(f"/api/clients/{client_a_id}/action-items")
        r_b = http.get(f"/api/clients/{client_b_id}/action-items")
        check(
            "GET action-items for Client A → 200",
            r_a.status_code == 200,
            r_a.text[:200],
        )
        check(
            "GET action-items for Client B → 200",
            r_b.status_code == 200,
            r_b.text[:200],
        )

        items_a = r_a.json().get("items", [])
        items_b = r_b.json().get("items", [])
        ids_a = {i["id"] for i in items_a}
        ids_b = {i["id"] for i in items_b}

        check(
            "No action item IDs shared between Client A and Client B",
            ids_a.isdisjoint(ids_b),
            f"Shared IDs: {ids_a & ids_b}",
        )

        wrong_a = [i for i in items_a if i.get("client_id") != client_a_id]
        wrong_b = [i for i in items_b if i.get("client_id") != client_b_id]
        check(
            "Every Client A action item has client_id == A",
            not wrong_a,
            f"Mismatched items: {[i['id'] for i in wrong_a]}",
        )
        check(
            "Every Client B action item has client_id == B",
            not wrong_b,
            f"Mismatched items: {[i['id'] for i in wrong_b]}",
        )

        # ══ 9. Timeline isolation ══════════════════════════════════════════════
        print("\n── 9. Timeline isolation ──")
        r_a = http.get(f"/api/clients/{client_a_id}/timeline")
        r_b = http.get(f"/api/clients/{client_b_id}/timeline")
        check("GET timeline for Client A → 200", r_a.status_code == 200, r_a.text[:200])
        check("GET timeline for Client B → 200", r_b.status_code == 200, r_b.text[:200])

        tl_a = r_a.json().get("items", [])
        tl_b = r_b.json().get("items", [])

        doc_names_in_tl_a = {
            i.get("filename") for i in tl_a if i.get("type") == "document"
        }
        doc_names_in_tl_b = {
            i.get("filename") for i in tl_b if i.get("type") == "document"
        }

        check(
            "Client A's document appears in Client A's timeline",
            "tax_memo_client_a.txt" in doc_names_in_tl_a,
            f"doc entries in timeline_a: {doc_names_in_tl_a}",
        )
        check(
            "Client B's document does NOT appear in Client A's timeline",
            "financial_report_client_b.txt" not in doc_names_in_tl_a,
            f"doc entries in timeline_a: {doc_names_in_tl_a}",
        )
        check(
            "Client B's document appears in Client B's timeline",
            "financial_report_client_b.txt" in doc_names_in_tl_b,
            f"doc entries in timeline_b: {doc_names_in_tl_b}",
        )
        check(
            "Client A's document does NOT appear in Client B's timeline",
            "tax_memo_client_a.txt" not in doc_names_in_tl_b,
            f"doc entries in timeline_b: {doc_names_in_tl_b}",
        )

        # Action item IDs must not cross timelines either
        tl_ai_ids_a = {i["id"] for i in tl_a if i.get("type") == "action_item"}
        tl_ai_ids_b = {i["id"] for i in tl_b if i.get("type") == "action_item"}
        check(
            "No action item IDs shared between Client A and B timelines",
            tl_ai_ids_a.isdisjoint(tl_ai_ids_b),
            f"Shared: {tl_ai_ids_a & tl_ai_ids_b}",
        )

        # ══ 10. Chat history isolation ════════════════════════════════════════
        print("\n── 10. Chat history isolation ──")
        r_a = http.get(f"/api/clients/{client_a_id}/chat-history")
        r_b = http.get(f"/api/clients/{client_b_id}/chat-history")
        check(
            "GET chat-history for Client A → 200",
            r_a.status_code == 200,
            r_a.text[:200],
        )
        check(
            "GET chat-history for Client B → 200",
            r_b.status_code == 200,
            r_b.text[:200],
        )

        hist_a = r_a.json().get("messages", [])
        hist_b = r_b.json().get("messages", [])

        check(
            "Client A has chat messages (from RAG tests above)",
            len(hist_a) > 0,
        )
        check(
            "Client B has chat messages (from RAG tests above)",
            len(hist_b) > 0,
        )

        msg_ids_a = {m["id"] for m in hist_a}
        msg_ids_b = {m["id"] for m in hist_b}
        check(
            "No chat message IDs shared between Client A and Client B",
            msg_ids_a.isdisjoint(msg_ids_b),
            f"Shared IDs: {msg_ids_a & msg_ids_b}",
        )

        wrong_msg_a = [m for m in hist_a if m.get("client_id") != client_a_id]
        wrong_msg_b = [m for m in hist_b if m.get("client_id") != client_b_id]
        check(
            "Every Client A chat message has client_id == A",
            not wrong_msg_a,
            f"Mismatched: {[m['id'] for m in wrong_msg_a]}",
        )
        check(
            "Every Client B chat message has client_id == B",
            not wrong_msg_b,
            f"Mismatched: {[m['id'] for m in wrong_msg_b]}",
        )

        all_b_text = " ".join(m.get("content", "") for m in hist_b)
        all_a_text = " ".join(m.get("content", "") for m in hist_a)
        check(
            "Client A's unique marker absent from Client B's chat history",
            CLIENT_A_MARKER not in all_b_text,
            f"Found {CLIENT_A_MARKER!r} in Client B history",
        )
        check(
            "Client B's unique marker absent from Client A's chat history",
            CLIENT_B_MARKER not in all_a_text,
            f"Found {CLIENT_B_MARKER!r} in Client A history",
        )

    finally:
        # ══ Cleanup ═══════════════════════════════════════════════════════════
        print("\n── Cleanup ──")
        for cid, name in [(client_a_id, "Client A"), (client_b_id, "Client B")]:
            if cid:
                r = http.delete(f"/api/clients/{cid}")
                if r.status_code in (200, 204):
                    print(f"  Deleted {name} ({cid})")
                else:
                    print(
                        f"  WARNING: Could not delete {name} ({cid}): "
                        f"{r.status_code} {r.text[:120]}"
                    )
        http.close()

    # ══ Summary ═══════════════════════════════════════════════════════════════
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = passed + failed

    print("\n" + "═" * 60)
    print(f"  {passed}/{total} checks passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
    else:
        print("  — all good!")
    print("═" * 60)

    if failed:
        print("\nFailed checks:")
        for label, ok, detail in _results:
            if not ok:
                print(f"  ✗  {label}")
                if detail:
                    print(f"       {detail}")
        return False
    return True


# ─── pytest entry point ───────────────────────────────────────────────────────

def test_client_isolation():
    """
    pytest-compatible wrapper.

    Requires TEST_MODE=true in backend/.env.local (no env vars needed at the shell).
    Run with:  pytest -s backend/tests/test_client_isolation.py
    """
    assert run_tests(), "One or more isolation checks failed — see output above."


# ─── Direct execution entry point ─────────────────────────────────────────────

if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
