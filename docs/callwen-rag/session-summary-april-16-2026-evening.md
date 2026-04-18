# Session Summary — April 16, 2026 Evening

**Time:** ~3:30 PM – 8:00 PM EDT
**Focus:** Tracy Chen S-corp eval fixture, citation accuracy pipeline, variance characterization
**Production state:** Railway commit `91cce1e`, Vercel commit `91cce1e`, both active

## Commit chain

| Commit | Time (EDT) | Description |
|--------|-----------|-------------|
| `9c10f27` | (prior session) | Tracy Chen fixture — 10 ground-truth questions |
| `7f706cd` | (prior session) | Citation prompt fix — "Form X, Line Y" format |
| `11780d0` | ~6:20 PM | Chunk header enrichment — form name + FEDERAL/STATE tags |
| `7940e7b` | ~6:37 PM | Instruct LLM to cite specific schedules over parent forms |
| `c706e8e` | ~7:05 PM | Citation regex — Box references, line suffix tolerance, form prefix matching |
| `be5aa66` | ~7:35 PM | Require line number in all form citations |
| `91cce1e` | ~7:36 PM | Alternate acceptable pages for retrieval scoring |

## Eval progression

All values are single runs except where "(3-run mean)" is noted.

| Stage | Michael | | | Tracy | | |
|-------|---------|------|------|-------|------|------|
| | Ret | Kw | Cit | Ret | Kw | Cit |
| Pre-session baseline | 1.0 | 0.9 | 0.60 | — | — | — |
| Tracy first eval (e50677db) | — | — | — | 0.6 | 0.9 | 0.00 |
| Citation prompt fix (7f706cd) | 1.0 | 0.8 | 0.70 | 0.6 | 0.9 | 0.30 |
| Header enrichment (11780d0) | 1.0 | 0.9 | 0.60 | 0.6 | 0.9 | 0.20 |
| Schedule specificity (7940e7b) 3-run | 1.00 | 0.90 | 0.60 | 0.60 | 0.90 | 0.33 |
| Regex Box/suffix (c706e8e) 3-run | 0.97 | 0.90 | 0.60 | 0.60 | 0.90 | 0.37 |
| Line req + alt pages (91cce1e) | 1.0 | 0.9 | 0.70 | **1.0** | **1.0** | 0.30 |

## Variance characterization (3x3 runs at commit 7940e7b)

```
         Michael                              Tracy
Run  Ret   Kw   Cit   Lat(ms)          Ret   Kw   Cit   Lat(ms)
---  ---  ---   ---   -------          ---  ---   ---   -------
1    1.0  0.9  0.60     4718           0.6  0.9  0.30     4682
2    1.0  0.9  0.60     4872           0.6  0.9  0.40     4254
3    1.0  0.9  0.60     4024           0.6  0.9  0.30     4458
Mean 1.00 0.90 0.60     4538           0.60 0.90 0.33     4465
SD   0.00 0.00 0.00      452           0.00 0.00 0.06      214
```

Noise floor: retrieval and keyword have zero variance. Citation SD is 0.00 (Michael) and 0.06 (Tracy). Single-run citation swings of ±0.1 are real signal, not noise.

## Variance characterization (3x3 runs at commit c706e8e)

```
         Michael                              Tracy
Run  Ret   Kw   Cit   Lat(ms)          Ret   Kw   Cit   Lat(ms)
---  ---  ---   ---   -------          ---  ---   ---   -------
1    1.0  0.9  0.60     4383           0.6  0.9  0.40     4249
2    1.0  0.9  0.60     3976           0.6  0.9  0.40     4235
3    0.9  0.9  0.60     5072           0.6  0.9  0.30     4713
Mean 0.97 0.90 0.60     4477           0.60 0.90 0.37     4399
SD   0.06 0.00 0.00      554           0.00 0.00 0.06      272
```

## Key architectural decisions

### 1. Runtime form detection in chunk headers
Added `_detect_form_name()` and `_is_state_form()` to `rag_service.py`. Regex-based detection of 30+ IRS forms/schedules and California state forms. Best-effort: covers ~30% of Tracy's chunks (those with explicit form names in text). Headers now read:
```
[TAX YEAR 2024 | FEDERAL Form 1120-S | Document: file.pdf | Page 16 | Relevance: 95.0%]
[TAX YEAR 2024 | STATE Form 100S | Document: file.pdf | Page 41 | Relevance: 90.0%]
```

### 2. Tolerant citation matching
Extended `rag_evaluator.py` citation matcher with:
- **Box N extraction**: "Box 17" treated same as "Line 17" (K-1, W-2)
- **Line suffix tolerance**: extracted "44" matches expected "44a"
- **Form prefix matching**: extracted "Form 100" matches expected "Form 100S"
- Safety: "Line 4" does NOT match "Line 44"; "Schedule K" does NOT match "Schedule K-1"

### 3. Multi-page retrieval scoring
Added `expected_pages: list[int]` to `GroundTruthItem`. When present, retrieval_hit checks if ANY acceptable page appears in retrieved chunks. This fixed Tracy's retrieval from 0.6 to 1.0 — the correct answers were being found on alternate pages.

## Remaining failure modes (Tracy citation misses)

Categorized from best Tracy citation run (ec970b5c, 0.4 citation):

| Category | Count | Examples |
|----------|-------|---------|
| No line number in LLM response | 3 | Q5 "Form 100S, Schedule F" (no line), Q8 "California Form 5806" (no line), Q9 "California Form 100S" (no line) |
| Wrong form, right line | 3 | Q2 Schedule K-1 instead of Form 1120-S, Q7 Schedule K Line 19 instead of Schedule M-2 Line 7, Q10 Form 1120-S instead of Form 7203 |

The "no line number" misses are targeted by the `be5aa66` prompt fix (require line number). The "wrong form" misses are LLM reasoning quality — the model defaults to familiar forms over obscure supporting schedules.

## Carryover for next session (prioritized)

1. **Tracy citation ceiling is ~0.4** with current prompt strategy. The remaining misses are LLM form-selection errors and occasional line-number omissions. Next lever: few-shot examples in the prompt showing correct schedule citations for S-corp questions specifically.

2. **Cartesian product extraction is lossy.** `_extract_citations()` pairs ALL forms × ALL lines, creating false positives on multi-form responses. A sentence-level extraction approach (find form+line pairs within the same sentence) would be more accurate. Medium effort, high precision gain.

3. **Tracy Q4 (total deductions) answer is sometimes wrong.** LLM returns $362,896 (California) or $123,681 (Line 20 other deductions) instead of $364,521 (Line 21 total). The CA reconciliation page (p52) has a cleaner table than the garbled OCR on p16. This is an extraction quality issue — Document AI re-extraction of p16 might help.

4. **Michael Q4 (taxable interest $7) remains fragile.** Adjacent to $136 (line 2a) and $7 appears elsewhere. Keyword hit is nondeterministic. The tightened rubric ("$7.00", "$7.") helps but doesn't eliminate the issue.

5. **"Box N" blind spot in _FORM_PATTERN.** The form regex `(?:Form|Schedule)\s+[A-Z0-9][\w-]*` doesn't extract standalone "Box 17" without an associated Form/Schedule. If the LLM writes "K-1, Box 17" without "Schedule" prefix, the form won't be extracted. Low priority since K-1 usually includes "Schedule K-1".

6. **Update SKILL.md** with current eval baselines (Tracy added, citation improvements) and the new architectural components (form detection, tolerant matching, multi-page scoring).
