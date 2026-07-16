"""
DAXDA Sandbox — Run Logger
Saves a complete structured JSON log and markdown summary for each sandbox run.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional


def _gate_str(gate) -> str:
    if hasattr(gate, "value"):
        return str(gate.value).upper()
    return str(gate).upper().replace("GATESTATE.", "")


def save_run_log(
    log_dir: str,
    run_id: str,
    test_name: str,
    test_number: int,
    input_text: str,
    result: dict,
    gap_analysis: dict,
    duration_seconds: float,
    cast_path: Optional[str] = None,
) -> str:
    """
    Saves a complete JSON log for one sandbox run.
    Returns the path to the saved file.
    """
    os.makedirs(log_dir, exist_ok=True)

    gate     = _gate_str(result.get("final_gate", "?"))
    score    = result.get("final_stability_score", 0.0)
    warnings = result.get("warnings", [])
    trace    = result.get("audit_manifest", {}).get("trace", [])

    log = {
        "run_id":              run_id,
        "test_number":         test_number,
        "test_name":           test_name,
        "timestamp_utc":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds":    round(duration_seconds, 4),
        "input_length_chars":  len(input_text),
        "input_preview":       input_text[:300],
        "final_gate":          gate,
        "final_stability_score": score,
        "authority_level":     str(result.get("authority_level", "")),
        "release_lock":        str(result.get("release_lock", "")),
        "status":              str(result.get("status", "")),
        "audit_complete":      result.get("audit_complete", False),
        "action_release_authorized": result.get("action_release_authorized", False),
        "warning_count":       len(warnings),
        "warnings":            warnings,
        "ops_executed":        len(trace),
        "gap_analysis":        gap_analysis,
        "cast_file":           cast_path,
    }

    path = os.path.join(log_dir, f"{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

    return path


def save_run_summary(
    log_dir: str,
    run_id: str,
    test_name: str,
    test_number: int,
    input_text: str,
    result: dict,
    gap_analysis: dict,
    duration_seconds: float,
    cast_path: Optional[str] = None,
) -> str:
    """
    Saves a human-readable markdown summary for one sandbox run.
    Returns the path to the saved file.
    """
    os.makedirs(log_dir, exist_ok=True)

    gate      = _gate_str(result.get("final_gate", "?"))
    score     = result.get("final_stability_score", 0.0)
    authority = str(result.get("authority_level", ""))
    lock      = str(result.get("release_lock", ""))
    status    = str(result.get("status", ""))
    warnings  = result.get("warnings", [])
    trace     = result.get("audit_manifest", {}).get("trace", [])

    gate_icon = {"BLOCK": "🔴", "PASS": "🟢", "RELEASE": "🟢",
                 "WARN": "🟡", "CAUTION": "🟠", "DEFERRED": "🟣"}.get(gate, "⚪")

    lines = [
        f"# DAXDA Sandbox Run {test_number:04d}",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Run ID | `{run_id}` |",
        f"| Test | {test_name} |",
        f"| Timestamp | {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} |",
        f"| Duration | {duration_seconds:.3f}s |",
        f"| Ops executed | {len(trace)} / 886 |",
        f"",
        f"## Decision",
        f"",
        f"| {gate_icon} Gate | Score | Authority | Lock | Status |",
        f"|--------|-------|-----------|------|--------|",
        f"| **{gate}** | {score:.4f} | {authority} | {lock} | {status} |",
        f"",
        f"## Input",
        f"",
        f"```",
        input_text[:600] + ("..." if len(input_text) > 600 else ""),
        f"```",
        f"",
        f"## Warnings ({len(warnings)})",
        f"",
    ]

    if warnings:
        for w in warnings[:30]:
            lines.append(f"- {w}")
        if len(warnings) > 30:
            lines.append(f"- *... and {len(warnings) - 30} more*")
    else:
        lines.append("*No warnings emitted.*")

    lines += [
        f"",
        f"## Gap Analysis",
        f"",
        f"```json",
        json.dumps(gap_analysis, indent=2),
        f"```",
    ]

    if cast_path:
        cast_name = os.path.basename(cast_path)
        lines += [
            f"",
            f"## Recording",
            f"",
            f"```",
            f"asciinema play {cast_name}",
            f"```",
        ]

    md = "\n".join(lines)
    path = os.path.join(log_dir, f"{run_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    return path


def save_session_index(log_dir: str, runs: list[dict]) -> str:
    """
    Saves/updates a session index markdown that lists all runs in this session.
    """
    os.makedirs(log_dir, exist_ok=True)

    lines = [
        "# DAXDA Sandbox — Session Index",
        f"",
        f"Last updated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"Runs in session: {len(runs)}",
        f"",
        f"| # | Run ID | Test | Gate | Score | Warnings | Duration |",
        f"|--:|--------|------|:----:|------:|---------:|---------:|",
    ]

    for r in runs:
        lines.append(
            f"| {r['test_number']:03d} "
            f"| `{r['run_id']}` "
            f"| {r['test_name'][:40]} "
            f"| {r['gate']} "
            f"| {r['score']:.4f} "
            f"| {r['warning_count']} "
            f"| {r['duration_seconds']:.2f}s |"
        )

    md = "\n".join(lines)
    path = os.path.join(log_dir, "SESSION_INDEX.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    return path
