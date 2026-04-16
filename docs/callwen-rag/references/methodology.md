# Callwen RAG — Debugging Methodology

Load this at the start of any live RAG debugging session. It is short on purpose. The disciplines here have repeatedly paid off across sessions, and the failure modes they prevent have repeatedly burned time.

## The core rule

**Data first, hypothesis second. Always.**

Every failed debugging session on this codebase has started with a hypothesis and skipped the data check. Every successful one has started with a SQL query, a log capture, or a chunk inspection, and let the data shape the hypothesis.

When a new hypothesis forms the moment data arrives, **stop and re-read the data**. The April 14 morning session killed three hypotheses in sequence — each one felt more confident than the last at the moment it was built, each one was falsified by the next piece of data. The slice bug was only found after forcing a full read of the RAG query → term expansion → hybrid search → keyword fallback logs for every question, correlating line by line against the code.

## Raw output discipline

Claude Code (and sometimes Claude in chat) will collapse long tool outputs. A `+100 lines (ctrl+o to expand)` or `[function shown]` is a cost multiplier, not a convenience. Each collapse costs 5-15 minutes of back-and-forth to re-extract the hidden content.

The workaround that works:

```bash
grep ... > /tmp/capture.txt
wc -l /tmp/capture.txt
sed -n '1,40p' /tmp/capture.txt    # first 40
sed -n '41,80p' /tmp/capture.txt   # next 40
# continue in 40-line chunks
```

Write to file first. Read in bounded chunks. Never rely on default rendering for multi-hundred-line output. Same pattern for `railway logs` — historical fetch (`--since Nm > /tmp/capture.log`) is deterministic; streaming disconnects silently and there is no indication it died.

## Verify before edit

Before any file change, read the file immediately prior. Earlier view output in context is stale after any write. For a non-trivial fix, also:

1. Verify current code around the edit site
2. Check dependency usage — if you're changing a function signature or a return type, grep the codebase for callers
3. Verify return types and data shapes via REPL if the fix depends on them

The April 15 late-night session locked in the `none_as_null=False` diagnosis with a three-line REPL check:

```python
>>> from sqlalchemy.dialects.postgresql import JSONB
>>> JSONB().none_as_null
False
>>> JSONB(none_as_null=True).none_as_null
True
```

Three seconds, saved hours.

## SQL pre-flight gate

When the proposed fix is a change to query construction, database interaction, or data transformation, run the *fix* as raw SQL against production first. Establish that it would move the needle before changing code.

The BM25 OR-join rewrite was gated on this pre-flight:

```sql
-- AND-join (current): 0-3 matches per query
SELECT COUNT(*) ... @@ plainto_tsquery('english', '<query>');
-- OR-join (proposed): 87-175 matches per query
SELECT COUNT(*) ... @@ to_tsquery('english', '<tokens joined with |>');
```

If the OR-join had returned 0-2 matches per query, the code change was not worth shipping. Because it returned 87-175, the change was worth shipping. Either way, the decision was made from data, not from hope.

**Apply this rule whenever you're tempted to ship a fix without concrete evidence the fix addresses the symptom.**

## Carryover as bug class, not line-number list

Session summaries carry forward "suspected cause" lists. Treat these as a *class* of bug to hunt, not a scavenger hunt of specific locations.

The April 15 late-night JSONB producer bug was in the model column definition. The carryover from the previous night listed three suspect files, none of them the model. If that session had pattern-matched on the three specific locations, eliminated them, and concluded "not here," the bug would have been declared unfindable. Instead, the carryover guided the *class* of hunt ("find the producer writing JSONB null"), the SQLAlchemy column default surfaced as a natural next step, and the bug was found.

When opening a session from a carryover: read the bug class, then widen the search aperture before narrowing.

## Resist "we're hot, keep shipping" momentum

After a fix lands cleanly, the temptation to immediately ship the next one in the same session is strong and usually wrong. Adjacent work feels free; it is not. Every additional phase in a session compounds the risk of an unreviewed change landing in the same commit chain.

Gate each phase with a check. The April 15 late-night session gated three:

1. After the JSONB producer fix landed, the audit of other `IS NULL` callers ran next (10 minutes, came back clean) before BM25 work started.
2. BM25 work was gated on the SQL pre-flight — if OR-join hadn't improved hit counts, the code change was scoped out.
3. After BM25 shipped, the temptation was to immediately fix Q4/Q9 prompt. Instead, the diagnostic step (read Q4/Q8 chunks) naturally surfaced that the rubric was wrong, not the system. That reframed the task and prevented a prompt change that would have been unnecessary.

## When you think you know the answer

If you form a hypothesis quickly and it feels obvious, that is the tell to slow down. Obvious hypotheses have been wrong on this codebase repeatedly. The bug you expect is rarely the bug that is there.

Specific examples from project history:
- "BM25 search_vector must be null post-reprocess" → actually populated 100%; the bug was AND-join tokenization.
- "JSONB null must be from `chunking.py:118`" → actually from the SQLAlchemy model's default `JSONB` type, a layer deeper.
- "Vector search and BM25 return zero — must be the reprocess pipeline" → actually the keyword fallback was the primary retrieval path and everyone misread the logs.

The pattern: the confident wrong hypothesis is usually one layer shallower than the real cause.

## Session hygiene checklist

For any RAG debugging session, open with:

1. Latest production commit (`git log origin/main -1 --oneline`)
2. Latest Railway deploy status (ACTIVE / BUILDING / FAILED)
3. Whether there are uncommitted local changes (`git status`)
4. Whether the ground-truth eval has been run recently and what it said

Close with:

1. Commit hash(es) shipped, in order
2. Eval delta measured (before / after)
3. Carryover items noted as *bug class*, not just file locations
4. Any credentials surfaced during the session flagged for rotation

This checklist is also the structure a good session summary follows. See `session-summary-april-15-2026-late-night.md` for a canonical example — load it if you need a template.
