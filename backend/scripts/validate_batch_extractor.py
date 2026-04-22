#!/usr/bin/env python3
"""
Session 3 validation: real DocAI batch call end-to-end.

Reads a test PDF from /tmp/session3_test.pdf, runs it through
BatchExtractor.extract() with real GCS + real DocAI batch, and
prints the returned dict shape + a summary for manual verification.

This script is NOT part of any production code path. It is a
one-off validation tool retained in the repo for future smoke
testing.

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS_JSON='...'
    export GOOGLE_CLOUD_PROJECT='advisoryboard-489516'
    export DOCAI_GCS_BUCKET='callwen-docai-staging'
    export DOCAI_OCR_PROCESSOR_ID='...'
    cd ~/advisoryboard-mvp-code/backend
    ./venv/bin/python scripts/validate_batch_extractor.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

# Make backend/app importable when running script directly
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.batch_extractor import BatchExtractor


TEST_PDF_PATH = Path("/tmp/session3_test.pdf")


def main() -> int:
    # Pre-flight checks
    if not TEST_PDF_PATH.exists():
        print(f"ERROR: test PDF not found at {TEST_PDF_PATH}")
        return 1

    for var in (
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "GOOGLE_CLOUD_PROJECT",
        "DOCAI_GCS_BUCKET",
        "DOCAI_OCR_PROCESSOR_ID",
    ):
        if not os.getenv(var):
            print(f"ERROR: env var {var} is not set")
            return 1

    file_bytes = TEST_PDF_PATH.read_bytes()
    file_size_kb = len(file_bytes) / 1024
    print(f"Test PDF: {TEST_PDF_PATH} ({file_size_kb:.1f} KB)")

    # Use OCR processor (simpler output shape than Form Parser)
    project_id = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.getenv("DOCAI_LOCATION", "us")
    processor_id = os.environ["DOCAI_OCR_PROCESSOR_ID"]
    processor_name = (
        f"projects/{project_id}/locations/{location}/processors/{processor_id}"
    )

    # Synthetic document_id (not tied to prod documents table)
    document_id = f"session3-validate-{uuid.uuid4().hex[:8]}"
    print(f"Synthetic document_id: {document_id}")
    print(f"Processor: {processor_name}")
    print(f"Bucket: {os.environ['DOCAI_GCS_BUCKET']}")

    # Instantiate with real factories (no mocks)
    print("\nInstantiating BatchExtractor with real GCS + DocAI clients...")
    extractor = BatchExtractor()
    print(f"  bucket_name: {extractor.bucket_name}")
    print(f"  poll_timeout: {extractor.poll_timeout}s")

    # Run the extraction
    print("\nCalling extract() — this may take 30-90s for a small PDF...")
    start = time.monotonic()
    try:
        result = extractor.extract(
            file_bytes=file_bytes,
            document_id=document_id,
            processor_name=processor_name,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"\nFAILED after {elapsed:.1f}s: {type(exc).__name__}: {exc}")
        return 2

    elapsed = time.monotonic() - start
    print(f"\nSUCCESS after {elapsed:.1f}s\n")

    # Inspect the result
    print("=" * 60)
    print("RESULT STRUCTURE")
    print("=" * 60)
    print(f"Top-level keys: {sorted(result.keys())}")
    print(f"Total text length: {len(result.get('text', ''))} chars")

    pages = result.get("pages", [])
    print(f"Pages returned: {len(pages)}")
    if pages:
        print(f"First page keys: {sorted(pages[0].keys())}")
        page_numbers = [p.get("page_number") for p in pages]
        print(f"Page numbers: {page_numbers}")
        print(f"Page numbers sorted: {page_numbers == sorted(page_numbers)}")

        # Empty-text check
        empty_pages = [p["page_number"] for p in pages if not p.get("text", "").strip()]
        if empty_pages:
            print(f"WARNING: pages with empty text: {empty_pages}")
        else:
            print("All pages have non-empty text")

        # Sample output
        print("\n" + "=" * 60)
        print("SAMPLE OUTPUT — first 400 chars of page 1")
        print("=" * 60)
        print(pages[0].get("text", "")[:400])

    print("\n" + "=" * 60)
    print("MANUAL VERIFICATION CHECKLIST")
    print("=" * 60)
    print("1. Does the page count match the PDF's actual page count?")
    print("2. Does the sample text above look like readable English tax form content?")
    print("3. Are there any garbled characters or offset artifacts?")
    print("4. Is any expected content missing?")
    print()
    print("If all 4 check out → Session 3 success.")
    print("If ANY fail → fix needed before Session 4 proceeds.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
