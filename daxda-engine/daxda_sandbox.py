#!/usr/bin/env python3
"""
DAXDA.IA — 886-Ops Sandbox
Nicole Protocol / Auto-Run Governance Benchmark

Continuously generates and runs DAXDA tests, displaying all 886 operations
in real time and recording each run as an asciinema .cast file + JSON log.

Usage:
    python3 daxda_sandbox.py                    # run forever, 12ms between ops
    python3 daxda_sandbox.py --runs 10          # 10 auto-generated runs
    python3 daxda_sandbox.py --delay 0          # max speed (no animation delay)
    python3 daxda_sandbox.py --delay 40         # slower, more readable
    python3 daxda_sandbox.py --mode full_886    # use LLM amalgamation (if available)
    python3 daxda_sandbox.py --no-record        # skip .cast file recording
    python3 daxda_sandbox.py --ticker 110       # score ticker every 110 ops (2×/layer)
"""
from __future__ import annotations
import argparse
import os
import sys
import time
import uuid
import json
import signal

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from core.engine import run_daxda_886
from sandbox.display import SandboxDisplay
from sandbox.trace_player import play_trace
from sandbox.recorder import MultiRecorder
from sandbox.run_logger import save_run_log, save_run_summary, save_session_index
from sandbox.test_generator import generate_next_test, analyse_gaps, GeneratedTest

# ── Directories ───────────────────────────────────────────────────────────────
LOG_DIR  = os.path.join(_ROOT, "daxda-engine", "sandbox", "run_logs")
CAST_DIR = os.path.join(_ROOT, "daxda-engine", "sandbox", "run_logs")

# ── Session state ─────────────────────────────────────────────────────────────
_session_runs: list[dict] = []
_interrupted  = False


def _handle_sigint(sig, frame):
    global _interrupted
    print("\n\n  ⏹  DAXDA Sandbox interrupted — finishing current run...\n")
    _interrupted = True


signal.signal(signal.SIGINT, _handle_sigint)


# ── Gate string helper ────────────────────────────────────────────────────────

def _gate_str(gate) -> str:
    if hasattr(gate, "value"):
        return str(gate.value).upper()
    return str(gate).upper().replace("GATESTATE.", "")


# ── Single run ────────────────────────────────────────────────────────────────

def run_one(
    test: GeneratedTest,
    run_number: int,
    total_runs: int | None,
    mode: str,
    delay_ms: float,
    ticker_every: int,
    record: bool,
) -> dict:
    """
    Execute one DAXDA run:
      1. Run the engine (gets 886-entry trace)
      2. Display trace in real time via trace_player
      3. Record to .cast + .log
      4. Save JSON log + markdown summary
      5. Return gap analysis for next test generator
    """
    run_id   = f"daxda-sb-{time.strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:6]}"
    cast_path = os.path.join(CAST_DIR, f"{run_id}.cast")
    log_path  = os.path.join(LOG_DIR,  f"{run_id}.log")

    # ── Init display ──────────────────────────────────────────────────────────
    display = SandboxDisplay(
        run_id=run_id,
        test_name=test.name,
        test_number=run_number,
        total_tests_planned=total_runs or 0,
        mode=mode,
    )

    # ── Init recorder ─────────────────────────────────────────────────────────
    recorder = None
    if record:
        os.makedirs(CAST_DIR, exist_ok=True)
        recorder = MultiRecorder(
            cast_path=cast_path,
            log_path=log_path,
            title=f"DAXDA Run {run_number:04d} — {test.name}",
        )
        recorder.start()

    # ── Print header ──────────────────────────────────────────────────────────
    display.print_header(test.input_text)

    # ── Execute engine ────────────────────────────────────────────────────────
    t0 = time.time()
    result = run_daxda_886(
        test.input_text,
        mode,
        None, None,
        "decision_request",
    )
    engine_duration = time.time() - t0

    trace = result.get("audit_manifest", {}).get("trace", [])

    # ── Play trace in real time ───────────────────────────────────────────────
    play_trace(trace, display, delay_ms=delay_ms, score_ticker_every=ticker_every)

    # ── Print final decision ──────────────────────────────────────────────────
    display.print_final_decision(result)

    total_duration = time.time() - t0

    # ── Flush captured lines to recorder ─────────────────────────────────────
    if recorder:
        recorder.write_lines(display.line_buffer)
        recorder.stop()

    # ── Gap analysis ──────────────────────────────────────────────────────────
    gap = analyse_gaps(result, test.name)

    # ── Save logs ─────────────────────────────────────────────────────────────
    save_run_log(
        log_dir=LOG_DIR,
        run_id=run_id,
        test_name=test.name,
        test_number=run_number,
        input_text=test.input_text,
        result=result,
        gap_analysis=gap,
        duration_seconds=total_duration,
        cast_path=cast_path if record else None,
    )
    save_run_summary(
        log_dir=LOG_DIR,
        run_id=run_id,
        test_name=test.name,
        test_number=run_number,
        input_text=test.input_text,
        result=result,
        gap_analysis=gap,
        duration_seconds=total_duration,
        cast_path=cast_path if record else None,
    )

    gate  = _gate_str(result.get("final_gate", "?"))
    score = result.get("final_stability_score", 0.0)

    run_entry = {
        "run_id":           run_id,
        "test_number":      run_number,
        "test_name":        test.name,
        "gate":             gate,
        "score":            score,
        "warning_count":    len(result.get("warnings", [])),
        "duration_seconds": round(total_duration, 3),
        "cast_path":        cast_path if record else None,
    }
    _session_runs.append(run_entry)

    # Update session index
    save_session_index(LOG_DIR, _session_runs)

    # Print run summary line
    print(
        f"\n  📁  Logs: {LOG_DIR}/{run_id}.[json|md]"
        + (f"\n  🎬  Recording: asciinema play {cast_path}" if record else "")
        + f"\n  ⏱  Engine: {engine_duration:.3f}s | Total: {total_duration:.1f}s\n"
    )

    return gap


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DAXDA 886-Ops Sandbox — auto-runs with live display and screen recording"
    )
    parser.add_argument("--runs",      type=int,   default=None,
                        help="Number of runs (default: infinite)")
    parser.add_argument("--delay",     type=float, default=12.0,
                        help="Milliseconds between tile renders (default: 12)")
    parser.add_argument("--mode",      type=str,   default="quick",
                        choices=["quick", "standard", "full_886", "dry_run"],
                        help="DAXDA runtime mode (default: quick)")
    parser.add_argument("--ticker",    type=int,   default=55,
                        help="Print score ticker every N ops (default: 55 = every layer)")
    parser.add_argument("--no-record", action="store_true",
                        help="Disable .cast screen recording")
    parser.add_argument("--seed-test", type=int,   default=None,
                        help="Force a specific test template index (0–14) for first run")
    args = parser.parse_args()

    record = not args.no_record
    total  = args.runs

    print(f"\n  ┌─────────────────────────────────────────────────┐")
    print(f"  │  DAXDA.IA  886-OPS SANDBOX  —  Nicole Protocol  │")
    print(f"  │  Mode: {args.mode:<10}  Delay: {args.delay}ms/op              │")
    print(f"  │  Runs: {'∞' if not total else total:<10}  Record: {'ON' if record else 'OFF'}                    │")
    print(f"  │  Logs: {LOG_DIR[-42:]}  │")
    print(f"  └─────────────────────────────────────────────────┘\n")
    print(f"  Press Ctrl+C to stop gracefully after current run.\n")

    # Initial gap — neutral (no prior run)
    gap: dict = {
        "last_gate": "PASS", "last_score": 0.5, "last_test": "none",
        "warning_count": 0,
        "adversarial_signals": 0, "financial_signals": 0,
        "legal_signals": 0, "evidence_signals": 0,
        "uncertainty_signals": 0, "escalation_signals": 0,
        "over_blocked": False, "under_blocked": False,
        "no_adversarial": True, "no_financial": True,
        "no_legal": True, "low_warnings": True, "high_warnings": False,
    }

    from sandbox.test_generator import ALL_TEMPLATES
    run_number = 0

    while True:
        run_number += 1

        if total and run_number > total:
            break

        # Generate next test
        if run_number == 1 and args.seed_test is not None:
            idx  = args.seed_test % len(ALL_TEMPLATES)
            test = ALL_TEMPLATES[idx](gap)
            reason = f"Seeded test (index {idx})"
        else:
            test   = generate_next_test(gap, run_number)
            reason = f"Gap-directed: {gap.get('last_test', 'initial')}"

        # Show next-test banner (after first run)
        if run_number > 1:
            # Borrow any existing display width
            from sandbox.display import SandboxDisplay as _D, _term_width
            _d = _D("", test.name, run_number, total or 0)
            _d.print_next_test_banner(test.name, reason, run_number, total)

        # Run it
        gap = run_one(
            test=test,
            run_number=run_number,
            total_runs=total,
            mode=args.mode,
            delay_ms=args.delay,
            ticker_every=args.ticker,
            record=record,
        )

        if _interrupted:
            break

    # Final session summary
    print(f"\n  ═══════════════════════════════════════════════════")
    print(f"  DAXDA Sandbox Session Complete")
    print(f"  Runs completed: {len(_session_runs)}")
    print(f"  Session index:  {LOG_DIR}/SESSION_INDEX.md")
    print(f"  ═══════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
