import pytest

from app.services.form_aware_chunker import _SectionFlipDetector


def test_detector_fires_on_schedule_a_oscillation():
    """Reproduces Michael Tjahjadi Schedule A page 10 oscillation
    pattern where bare amount-column numbers (5,6,7,8,9,10 emitted
    as standalone OCR lines) trigger rapid flip-flopping between
    'Taxes You Paid - Lines 5-7' and 'Interest You Paid - Lines 8-10'.

    Synthetic sequence alternates sections 5+ times within the
    10-line window, which should trigger at least one alert."""

    d = _SectionFlipDetector(window_lines=10, flip_threshold=2)

    # Simulate oscillating sequence:
    #   lines observed in order reflect what the chunker commits
    #   when OCR emits bare single-digit lines matching different
    #   section line-number ranges
    sections = [
        "Taxes You Paid - Lines 5-7",
        "Interest You Paid - Lines 8-10",
        "Taxes You Paid - Lines 5-7",
        "Interest You Paid - Lines 8-10",
        "Taxes You Paid - Lines 5-7",
        "Interest You Paid - Lines 8-10",
        "Taxes You Paid - Lines 5-7",
        "Interest You Paid - Lines 8-10",
        "Taxes You Paid - Lines 5-7",
        "Interest You Paid - Lines 8-10",
    ]
    for i, s in enumerate(sections):
        d.observe(section=s, line_no=None, raw_line=str(i),
                  form_type="Schedule A", page=10)

    assert len(d.alerts) >= 1, (
        f"Detector did not fire on known oscillation pattern. "
        f"Alerts: {d.alerts}"
    )
    # Sanity: the alert should record the right form and page
    assert d.alerts[0]["form"] == "Schedule A"
    assert d.alerts[0]["page"] == 10
    assert d.alerts[0]["revisit_count"] >= 2


def test_detector_quiet_on_normal_single_column_form():
    """Form 1040 main -- single-column, same section for many lines,
    then one legitimate section change. Must NOT fire."""

    d = _SectionFlipDetector(window_lines=10, flip_threshold=2)

    # 10 observations in Section A, then 1 transition, then 10 in B
    for i in range(10):
        d.observe(section="Income - Lines 1-9", line_no=None,
                  raw_line=str(i), form_type="Form 1040", page=1)
    for i in range(10):
        d.observe(section="Tax and Credits - Lines 12-22",
                  line_no=None, raw_line=str(i + 10),
                  form_type="Form 1040", page=2)

    assert len(d.alerts) == 0, (
        f"Detector fired on normal single-column form. "
        f"False positives: {d.alerts}"
    )


def test_detector_threshold_boundary():
    """flip_threshold=2 means 2+ revisits within the 10-line window
    triggers an alert. Exactly 1 revisit should NOT fire; exactly 2
    should."""

    # Case 1: exactly 1 revisit -- quiet
    d1 = _SectionFlipDetector(window_lines=10, flip_threshold=2)
    seq_1_revisit = ["A", "A", "B", "B", "A", "A", "C", "C", "D", "D"]
    # runs: A→B→A→C→D = 5. distinct: A,B,C,D = 4. revisits = 1.
    for i, s in enumerate(seq_1_revisit):
        d1.observe(section=s, line_no=None, raw_line=str(i),
                   form_type="Test", page=1)
    assert len(d1.alerts) == 0, (
        f"Detector fired at 1 revisit (below threshold=2). "
        f"Alerts: {d1.alerts}"
    )

    # Case 2: exactly 2 revisits -- fires
    d2 = _SectionFlipDetector(window_lines=10, flip_threshold=2)
    seq_2_revisits = ["A", "A", "B", "B", "A", "A", "B", "B", "C", "C"]
    # runs: A→B→A→B→C = 5. distinct: A,B,C = 3. revisits = 2.
    for i, s in enumerate(seq_2_revisits):
        d2.observe(section=s, line_no=None, raw_line=str(i),
                   form_type="Test", page=1)
    assert len(d2.alerts) >= 1, (
        f"Detector did NOT fire at 2 revisits (at threshold). "
        f"Alerts: {d2.alerts}"
    )


def test_detector_quiet_on_sequential_progression():
    """Multi-section document with granular per-line sections
    (like Form 1040 main). Every line has a different section
    (sequential progression A-B-C-D-...) but no oscillation.
    Must NOT fire."""
    d = _SectionFlipDetector(window_lines=10, flip_threshold=2)
    sections = ["Header", "Income", "Wages 1a-1z", "Interest 2a-2b",
                "Dividends 3a-3b", "IRA 4a-4b", "Pensions 5a-5b",
                "SS 6a-6c", "Capital Gain 7", "Additional 8"]
    for i, s in enumerate(sections):
        d.observe(section=s, line_no=None, raw_line=str(i),
                  form_type="Form 1040", page=1)
    assert len(d.alerts) == 0, (
        f"Detector fired on sequential progression "
        f"(Form 1040-style). False positives: {d.alerts}"
    )


def test_detector_fires_on_run_based_oscillation():
    """Schedule A-style run-based oscillation: v2 chunker's section
    lookup maps line ranges to sections, so oscillation manifests as
    runs of 3 same-section lines alternating, not per-line alternation.

    Pattern: [TP*3, IP*3, TP*3, IP*1] within a 10-line window.
    runs=4, distinct=2, revisits=2. Must fire at threshold=2."""
    d = _SectionFlipDetector(window_lines=10, flip_threshold=2)
    sections = ["TP", "TP", "TP", "IP", "IP", "IP", "TP", "TP", "TP", "IP"]
    for i, s in enumerate(sections):
        d.observe(section=s, line_no=None, raw_line=str(i),
                  form_type="Schedule A", page=10)
    assert len(d.alerts) >= 1, (
        f"Detector did not fire on run-based oscillation. "
        f"Alerts: {d.alerts}"
    )
