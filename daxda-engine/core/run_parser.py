"""
DAXDA.IA — Bounded Run Parser
Nicole Protocol / 886-Ops Architecture

Fixes the unbounded-parsing problem where Run A absorbs Run B and Run C text.

Rules:
  • Each run section is bounded: starts at "# RUN X" and ends at the NEXT
    "# RUN" or "# REQUIRED OUTPUT" or end-of-string.
  • Source blocks are extracted from within their bounded run section only.
  • Source IDs are preserved for tracing but are never used in gate logic.
"""
from __future__ import annotations
import re
from .source_classifier import Source


# ── Run section boundaries ────────────────────────────────────────────────────

# Matches "# RUN A", "# RUN B", "# RUN C" (with optional suffix)
_RUN_HEADER = re.compile(r'^#\s+RUN\s+([A-Z])\b.*$', re.MULTILINE)

# Marks the end of all run sections
_SECTION_END_MARKERS = re.compile(
    r'^#\s+(REQUIRED OUTPUT|CONSTRAINTS|TRUSTED TASK CONTRACT|SCENARIO)\b', re.MULTILINE | re.I)

# Matches [Source X1 — label text] or [Source X1: label text]
_SOURCE_BLOCK = re.compile(
    r'\[Source\s+([A-Z]\d+)\s*[—–-]\s*([^\]]+)\]\s*(.*?)(?=\[Source\s+[A-Z]\d+|\Z)',
    re.DOTALL | re.I)


def parse_runs(raw_text: str) -> dict[str, str]:
    """
    Split raw packet text into bounded run sections.

    Returns a dict like:
        {"RUN_A": "...text only for run A...",
         "RUN_B": "...text only for run B...",
         "RUN_C": "...text only for run C..."}

    Each value contains only the text between its header and the next
    run header (or section-end marker). Run A cannot absorb Run B text.
    """
    # Find all section end markers first
    end_markers: list[int] = [m.start() for m in _SECTION_END_MARKERS.finditer(raw_text)]

    # Find all run headers
    run_headers: list[tuple[str, int]] = [
        (m.group(1), m.start()) for m in _RUN_HEADER.finditer(raw_text)
    ]

    if not run_headers:
        return {}

    runs: dict[str, str] = {}
    for i, (run_letter, start_pos) in enumerate(run_headers):
        # The end of this run is the start of the next run, or the first
        # section-end marker after this start, whichever comes first
        candidates = []

        # Next run header
        if i + 1 < len(run_headers):
            candidates.append(run_headers[i + 1][1])

        # First section-end marker after start_pos
        for em in end_markers:
            if em > start_pos:
                candidates.append(em)
                break

        end_pos = min(candidates) if candidates else len(raw_text)
        run_text = raw_text[start_pos:end_pos].strip()
        runs[f"RUN_{run_letter}"] = run_text

    return runs


def parse_sources_from_run(run_text: str) -> list[Source]:
    """
    Extract individual source blocks from a bounded run section.

    Each [Source XN — label] block becomes a Source object.
    Source IDs are stored for trace output only and are never used
    in classification or gate logic.
    """
    sources: list[Source] = []

    for m in _SOURCE_BLOCK.finditer(run_text):
        source_id = m.group(1).strip()     # e.g. "A1", "B4"
        label     = m.group(2).strip()     # e.g. "Verified evaluation telemetry"
        body      = m.group(3).strip()     # Source content text

        sources.append(Source(
            source_id=source_id,
            label=label,
            text=body,
        ))

    return sources


def parse_all_runs(raw_text: str) -> dict[str, list[Source]]:
    """
    Parse raw packet text into a dict of run_name → [Source, ...].

    Example:
        {
            "RUN_A": [Source("A1", "Verified telemetry", "..."), ...],
            "RUN_B": [Source("B1", "Vendor statement", "..."), ...],
            "RUN_C": [Source("C1", "Runtime memory fragment", "..."), ...],
        }
    """
    run_texts = parse_runs(raw_text)
    return {
        run_name: parse_sources_from_run(run_text)
        for run_name, run_text in run_texts.items()
    }


def verify_run_isolation(raw_text: str) -> dict:
    """
    Verify that run boundaries are correctly isolated.

    Returns a diagnostic dict:
        {
            "isolated": True/False,
            "runs_found": ["RUN_A", "RUN_B", "RUN_C"],
            "cross_contamination": []  # list of issues if any
        }
    """
    runs = parse_runs(raw_text)
    issues = []

    for run_name, run_text in runs.items():
        other_run_letters = [
            k.replace("RUN_", "")
            for k in runs
            if k != run_name
        ]
        for letter in other_run_letters:
            # Check if a source from another run appears in this run's bounded text
            intruder = re.search(rf'\[Source {letter}\d+', run_text, re.I)
            if intruder:
                issues.append({
                    "run": run_name,
                    "intruder": f"Source {letter}N",
                    "snippet": run_text[max(0, intruder.start()-20):intruder.start()+30],
                })

    return {
        "isolated": len(issues) == 0,
        "runs_found": list(runs.keys()),
        "source_counts": {
            rn: len(parse_sources_from_run(rt))
            for rn, rt in runs.items()
        },
        "cross_contamination": issues,
    }
