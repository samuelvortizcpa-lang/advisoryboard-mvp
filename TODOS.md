# Callwen — Backlog

Last updated: 2026-03-28

## Security (from AUDIT-2026-03-28.md)

### CRITICAL — Fixed
- [x] C1/H1: OAuth CSRF nonce (fixed in af15d3a)
- [x] C2: HNSW vector index on document_chunks.embedding (fixed in af15d3a)
- [x] C3: Stripe webhook error handling — return 500 on failure (fixed in af15d3a)

### HIGH — Open
- [ ] H2: Upgrade Next.js 14 → 15.5.14+ (7 known CVEs including SSRF, request smuggling, DoS)
- [x] H3: Briefs router auth — already fixed in Sprint 1; alerts router migrated to org-aware auth
- [x] H4: Consent signing token brute-force — rate limiting + enumeration protection added
- [x] H5/H6: Add missing indexes — org_members/client_access (af15d3a) + 6 more perf indexes
- [x] H7: Alerts query optimization — merged queries + 60s TTL cache
- [ ] H8: Silent exception swallowing in document backfill (`except Exception: pass`)

### MEDIUM — Open
- [ ] M1: Admin API key timing attack — use hmac.compare_digest()
- [ ] M2: JWT audience (aud) verification disabled
- [ ] M3: Consent status/type accepts arbitrary strings — §7216 compliance risk
- [ ] M4: Localhost CORS origins in production
- [ ] M5: Unsanitized filename in Content-Disposition headers
- [ ] M6: Client types not org-scoped
- [ ] M7: Untyped org settings dict — no schema validation
- [ ] M8: Chat history visible/deletable cross-user
- [ ] M9: In-memory pagination in timeline
- [ ] M10: Unhandled date parsing in usage API
- [ ] M11: Test mode bypass is case-sensitive
- [ ] M12: N+1 lazy-loaded chunk.document in RAG pipeline
- [ ] M13: N+1 individual TaxStrategy lookups in loop
- [ ] M14: Unbounded .all() in brief generation
- [ ] M15: Broad exception catch on document download
- [ ] M16: Clerk Secret Key in proxy headers (edge log exposure)

## Performance
- [ ] OCR worker for scanned PDF extraction (replace pdfplumber with Tesseract pipeline)
- [ ] Async SQLAlchemy migration for backend concurrency
- [ ] H5/H6 indexes (see Security above)
- [ ] H7/M12/M13 N+1 query fixes (see Security above)

## Testing
- [ ] Frontend component tests (React Testing Library)
- [ ] Expand backend test coverage beyond current 43 unit tests
- [ ] E2E tests with Playwright

## Infrastructure
- [ ] Next.js 14 → 15 upgrade (see H2 above)
- [ ] Admin dashboard expansion (user management, analytics, audit logs)
- [ ] Remove unused backend deps: boto3, google-genai
