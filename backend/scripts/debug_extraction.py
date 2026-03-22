#!/usr/bin/env python3
"""
Diagnostic script: show exactly what text the RAG pipeline extracts
from a document, page by page, plus the generated chunks.

Usage:
    cd backend
    python scripts/debug_extraction.py <document_id>
    python scripts/debug_extraction.py --filename "2024 Tax Return"
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.services.text_extraction import extract_text, _extract_pdf, _is_garbled
from app.services.chunking import chunk_text, get_chunk_params
from app.services import storage_service


def get_session() -> Session:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL is required")
        sys.exit(1)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


def find_document(db: Session, doc_id: str | None, filename: str | None):
    if doc_id:
        row = db.execute(
            text("SELECT id, filename, file_path, file_type, document_type, processed FROM documents WHERE id = :did"),
            {"did": doc_id},
        ).fetchone()
    elif filename:
        row = db.execute(
            text("SELECT id, filename, file_path, file_type, document_type, processed FROM documents WHERE filename ILIKE :pat ORDER BY upload_date DESC LIMIT 1"),
            {"pat": f"%{filename}%"},
        ).fetchone()
    else:
        print("ERROR: provide --id or --filename")
        sys.exit(1)

    if not row:
        print("ERROR: document not found")
        sys.exit(1)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("doc_id", nargs="?", help="Document UUID")
    parser.add_argument("--filename", "-f", help="Search by filename (partial match)")
    args = parser.parse_args()

    db = get_session()
    doc = find_document(db, args.doc_id, args.filename)

    doc_id, filename, file_path, file_type, doc_type, processed = doc
    print(f"Document: {filename}")
    print(f"  ID: {doc_id}")
    print(f"  Type: {file_type} | Classification: {doc_type}")
    print(f"  Processed: {processed}")
    print(f"  Storage path: {file_path}")

    # Download and extract
    print("\n" + "=" * 70)
    print("STEP 1: Download and extract text")
    print("=" * 70)

    temp_path = storage_service.get_temp_local_path(file_path)
    try:
        full_text = extract_text(temp_path, file_type)
    finally:
        os.unlink(temp_path)

    print(f"\nTotal extracted text: {len(full_text)} chars")

    # Show page-by-page if markers exist
    import re
    page_sections = re.split(r"(\[Page \d+\])", full_text)
    if len(page_sections) > 1:
        print(f"\nFound page markers in extracted text")
        current_marker = None
        for section in page_sections:
            if re.match(r"\[Page \d+\]", section):
                current_marker = section
            elif current_marker and section.strip():
                print(f"\n{'─' * 60}")
                print(f"{current_marker} ({len(section.strip())} chars)")
                print("─" * 60)
                # Show first 800 chars of each page
                preview = section.strip()[:800]
                print(preview)
                if len(section.strip()) > 800:
                    print(f"  ... ({len(section.strip()) - 800} more chars)")

                # Check if this page looks garbled
                if _is_garbled(section.strip()):
                    print("  ⚠ THIS PAGE TEXT IS GARBLED")
                else:
                    print("  ✓ Page text looks clean")
    else:
        # No page markers — show first 2000 chars
        print("\nNo page markers found (old extraction format)")
        print(full_text[:2000])
        if len(full_text) > 2000:
            print(f"\n... ({len(full_text) - 2000} more chars)")

    # Check for key tax form content
    print("\n" + "=" * 70)
    print("STEP 2: Key content check")
    print("=" * 70)
    checks = [
        ("Form 1040", r"(?i)form\s*1040"),
        ("Line 11 / AGI", r"(?i)(line\s*11|adjusted\s*gross\s*income|agi)"),
        ("Line 9 / Total Income", r"(?i)(line\s*9|total\s*income)"),
        ("Line 15 / Taxable Income", r"(?i)(line\s*15|taxable\s*income)"),
        ("Schedule C", r"(?i)schedule\s*c"),
        ("Form 5329", r"(?i)form\s*5329"),
        ("Form 8995", r"(?i)form\s*8995"),
    ]
    for label, pattern in checks:
        matches = re.findall(pattern, full_text)
        if matches:
            # Find surrounding context
            match = re.search(pattern, full_text)
            start = max(0, match.start() - 50)
            end = min(len(full_text), match.end() + 100)
            context = full_text[start:end].replace("\n", " ")
            print(f"  ✓ {label}: found ({len(matches)} matches)")
            print(f"    Context: ...{context}...")
        else:
            print(f"  ✗ {label}: NOT FOUND")

    # Chunk the text
    print("\n" + "=" * 70)
    print("STEP 3: Chunking")
    print("=" * 70)
    chunk_size, chunk_overlap = get_chunk_params(doc_type)
    chunks = chunk_text(full_text, chunk_size, chunk_overlap)
    print(f"Chunk params: size={chunk_size}, overlap={chunk_overlap}")
    print(f"Total chunks: {len(chunks)}")

    # Show chunks that contain AGI/Line 11 content
    agi_chunks = []
    for i, c in enumerate(chunks):
        if re.search(r"(?i)(line\s*11|adjusted\s*gross|agi)", c):
            agi_chunks.append((i, c))

    if agi_chunks:
        print(f"\nChunks containing AGI/Line 11 content: {len(agi_chunks)}")
        for idx, chunk in agi_chunks:
            print(f"\n  Chunk {idx} ({len(chunk)} chars):")
            print(textwrap.indent(chunk[:500], "    "))
    else:
        print("\n  ⚠ NO CHUNKS contain AGI/Line 11 content!")

    # Show existing chunks in DB
    print("\n" + "=" * 70)
    print("STEP 4: Stored chunks in database")
    print("=" * 70)
    stored = db.execute(
        text("SELECT chunk_index, LEFT(chunk_text, 200) FROM document_chunks WHERE document_id = :did ORDER BY chunk_index"),
        {"did": str(doc_id)},
    ).fetchall()
    print(f"Stored chunks: {len(stored)}")
    for idx, preview in stored[:5]:
        print(f"  [{idx}] {preview[:150].replace(chr(10), ' ')}...")

    # Check stored chunks for AGI
    stored_agi = db.execute(
        text("SELECT chunk_index, chunk_text FROM document_chunks WHERE document_id = :did AND chunk_text ILIKE '%line 11%' OR (document_id = :did AND chunk_text ILIKE '%adjusted gross%')"),
        {"did": str(doc_id)},
    ).fetchall()
    if stored_agi:
        print(f"\n  Stored chunks with AGI content: {len(stored_agi)}")
        for idx, ct in stored_agi:
            print(f"    [{idx}] {ct[:200].replace(chr(10), ' ')}...")
    else:
        print("\n  ⚠ NO stored chunks contain AGI/Line 11!")

    db.close()


if __name__ == "__main__":
    main()
