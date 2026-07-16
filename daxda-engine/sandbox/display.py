"""
DAXDA Sandbox — Terminal Display
ANSI-native live dashboard. No external dependencies.
Falls back gracefully to plain text if ANSI is unsupported.
"""
from __future__ import annotations
import os
import sys
import time
import shutil
import textwrap
from typing import Optional

# ── ANSI colour palette ────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

# Foreground colours
FG_WHITE   = "\033[97m"
FG_CYAN    = "\033[96m"
FG_GREEN   = "\033[92m"
FG_YELLOW  = "\033[93m"
FG_RED     = "\033[91m"
FG_MAGENTA = "\033[95m"
FG_BLUE    = "\033[94m"
FG_GREY    = "\033[90m"
FG_ORANGE  = "\033[38;5;208m"

# Background colours
BG_DARK  = "\033[48;5;234m"
BG_NAVY  = "\033[48;5;17m"
BG_RED   = "\033[48;5;52m"
BG_GREEN = "\033[48;5;22m"

# ── Gate colours ──────────────────────────────────────────────────────────────
GATE_COLOUR = {
    "PASS":     FG_GREEN,
    "RELEASE":  FG_GREEN,
    "WARN":     FG_YELLOW,
    "CAUTION":  FG_ORANGE,
    "BLOCK":    FG_RED,
    "DEFERRED": FG_MAGENTA,
    "HALT":     FG_RED,
}

GATE_ICON = {
    "PASS":     "✓",
    "RELEASE":  "✓",
    "WARN":     "⚠",
    "CAUTION":  "◈",
    "BLOCK":    "✗",
    "DEFERRED": "⇢",
    "HALT":     "⛔",
}

LAYER_ABBREV = {
    "FDL_1": "FDL", "AML_1": "AML", "SIL_1": "SIL", "VEL_1": "VEL",
    "CEL_1": "CEL", "PVL_1": "PVL", "SAL_1": "SAL", "OIL_1": "OIL",
    "FDL_2": "FDL₂","AML_2": "AML₂","SIL_2": "SIL₂","VEL_2": "VEL₂",
    "CEL_2": "CEL₂","PVL_2": "PVL₂","SAL_2": "SAL₂","OIL_2": "OIL₂",
    "SYSTEM": "SYS",
}


def _term_width() -> int:
    return min(shutil.get_terminal_size((120, 40)).columns, 160)


def _gate_str(gate) -> str:
    if hasattr(gate, "value"):
        return str(gate.value).upper()
    return str(gate).upper().replace("GATESTATE.", "")


def _bar(filled: int, total: int, width: int = 30,
         full_char: str = "█", empty_char: str = "░") -> str:
    pct = filled / max(1, total)
    n = int(width * pct)
    return full_char * n + empty_char * (width - n)


def _centre(text: str, width: int) -> str:
    pad = max(0, (width - len(text)) // 2)
    return " " * pad + text


# ── Main display class ─────────────────────────────────────────────────────────

class SandboxDisplay:
    """
    Streams DAXDA's 886-op trace to the terminal as it plays back.
    Writes every line to a buffer so the recorder can capture it.
    """

    def __init__(self, run_id: str, test_name: str, test_number: int,
                 total_tests_planned: int, mode: str = "quick"):
        self.run_id = run_id
        self.test_name = test_name
        self.test_number = test_number
        self.total_tests_planned = total_tests_planned
        self.mode = mode
        self.width = _term_width()
        self.line_buffer: list[str] = []  # captured for recorder

        self._layer_count = 0
        self._tile_count = 0
        self._warning_count = 0
        self._recent_warnings: list[str] = []
        self._current_score = 0.0
        self._current_gate = "PASS"

    # ── Output helpers ─────────────────────────────────────────────────────────

    def _emit(self, line: str = ""):
        """Print and capture."""
        print(line)
        self.line_buffer.append(line + "\n")

    def _rule(self, char: str = "─", colour: str = FG_GREY) -> str:
        return colour + (char * self.width) + RESET

    def _box_line(self, content: str, colour: str = FG_CYAN) -> str:
        w = self.width - 4
        content = content[:w]
        return colour + "║ " + RESET + content.ljust(w) + colour + " ║" + RESET

    # ── Header ────────────────────────────────────────────────────────────────

    def print_header(self, input_preview: str):
        self._emit()
        self._emit(FG_CYAN + "╔" + "═" * (self.width - 2) + "╗" + RESET)
        self._emit(self._box_line(
            f"{BOLD}DAXDA.IA  ·  886-OPS SANDBOX{RESET}{FG_CYAN}  ·  Nicole Protocol",
            FG_CYAN))
        self._emit(self._box_line(
            f"Run {self.test_number:03d}  ·  {self.run_id}", FG_CYAN))
        self._emit(self._box_line(
            f"Mode: {self.mode.upper()}  ·  16 layers × 55 tiles + 6 system ops  =  886 operations",
            FG_CYAN))
        self._emit(FG_CYAN + "╠" + "═" * (self.width - 2) + "╣" + RESET)

        preview = input_preview[:self.width - 8].rstrip()
        for chunk in textwrap.wrap(preview, self.width - 8) or ["(empty)"]:
            self._emit(self._box_line(f"{FG_GREY}❝  {chunk}{RESET}", FG_CYAN))

        self._emit(FG_CYAN + "╚" + "═" * (self.width - 2) + "╝" + RESET)
        self._emit()

    # ── Layer transition banner ───────────────────────────────────────────────

    def print_layer_start(self, layer_id: str, layer_num: int):
        self._layer_count = layer_num
        abbrev = LAYER_ABBREV.get(layer_id, layer_id)
        bar = _bar(layer_num, 16, width=24)
        line = (
            f"  {FG_BLUE}▶  Layer {layer_num:02d}/16  [{abbrev:>5}]  "
            f"{FG_GREY}{bar}{RESET}  "
            f"{FG_GREY}tile 0/55{RESET}"
        )
        self._emit(line)

    # ── Tile operation line ───────────────────────────────────────────────────

    def print_tile(self, entry: dict, tile_idx_in_layer: int, abs_op: int):
        tile_id      = entry.get("tile_id", "?")
        fn_name      = entry.get("function_name", "?")
        layer_id     = entry.get("layer_id", "?")
        gate         = _gate_str(entry.get("gate", "PASS"))
        notes        = entry.get("notes", "")
        warnings     = entry.get("warnings", [])
        score_after  = entry.get("score_after", {})

        # Track warnings
        for w in warnings:
            self._warning_count += 1
            self._recent_warnings.append(w)
            if len(self._recent_warnings) > 8:
                self._recent_warnings.pop(0)

        # Score
        if isinstance(score_after, dict):
            dr = score_after.get("decision_readiness", self._current_score)
            if isinstance(dr, (int, float)):
                self._current_score = float(dr)

        gate_col  = GATE_COLOUR.get(gate, FG_WHITE)
        gate_icon = GATE_ICON.get(gate, "·")
        self._current_gate = gate

        # Tile bar
        tile_bar = _bar(tile_idx_in_layer, 55, width=14)

        # Truncate notes
        max_note = self.width - 70
        note_str = notes[:max_note] if notes else ""

        line = (
            f"  {FG_GREY}[{abs_op:04d}] "
            f"{FG_BLUE}{tile_id:<12}{RESET}  "
            f"{FG_WHITE}{fn_name:<30}{RESET}  "
            f"{gate_col}{gate_icon} {gate:<8}{RESET}  "
            f"{FG_GREY}{tile_bar}  {note_str[:max_note]}{RESET}"
        )
        self._emit(line)

        # Print warnings inline
        for w in warnings:
            warn_line = (
                f"  {FG_YELLOW}  ⚑ {FG_ORANGE}{w[:self.width - 10]}{RESET}"
            )
            self._emit(warn_line)

    # ── System ops ────────────────────────────────────────────────────────────

    def print_system_op(self, entry: dict, sys_op_num: int):
        tile_id  = entry.get("tile_id", f"SYS_{sys_op_num:03d}")
        fn_name  = entry.get("function_name", "system_op")
        gate     = _gate_str(entry.get("gate", "PASS"))
        notes    = entry.get("notes", "")
        gate_col = GATE_COLOUR.get(gate, FG_WHITE)
        gate_icon = GATE_ICON.get(gate, "·")

        line = (
            f"  {FG_MAGENTA}[SYS:{sys_op_num}]{RESET} "
            f"{FG_MAGENTA}{fn_name:<30}{RESET}  "
            f"{gate_col}{gate_icon} {gate:<8}{RESET}  "
            f"{FG_GREY}{notes[:self.width - 60]}{RESET}"
        )
        self._emit(line)

    # ── Score ticker (printed every N ops) ───────────────────────────────────

    def print_score_ticker(self, abs_op: int):
        gate_col  = GATE_COLOUR.get(self._current_gate, FG_WHITE)
        score_bar = _bar(int(self._current_score * 40), 40, width=40,
                         full_char="▓", empty_char="░")
        line = (
            f"\n  {FG_GREY}── OPS: {abs_op:04d}/886  "
            f"SCORE: {FG_WHITE}{self._current_score:.3f}  "
            f"{gate_col}{score_bar}  "
            f"WARNINGS: {FG_YELLOW}{self._warning_count}{RESET}\n"
        )
        self._emit(line)

    # ── Final decision banner ─────────────────────────────────────────────────

    def print_final_decision(self, result: dict):
        gate      = _gate_str(result.get("final_gate", "?"))
        score     = result.get("final_stability_score", 0.0)
        authority = str(result.get("authority_level", "?"))
        lock      = str(result.get("release_lock", "?"))
        status    = str(result.get("status", "?"))
        action_auth = result.get("action_release_authorized", False)

        gate_col = GATE_COLOUR.get(gate, FG_WHITE)
        bg       = BG_RED if gate == "BLOCK" else (BG_GREEN if gate in ("PASS", "RELEASE") else BG_NAVY)

        self._emit()
        self._emit(self._rule("═", gate_col))
        self._emit()
        self._emit(_centre(f"{bg}{BOLD}{gate_col}  ◈  DAXDA FINAL DECISION  ◈  {RESET}", self.width))
        self._emit()
        self._emit(_centre(f"{gate_col}{BOLD}GATE:  {gate}   │   SCORE: {score:.4f}   │   AUTHORITY: {authority}{RESET}", self.width))
        self._emit(_centre(f"{FG_GREY}Release lock: {lock}   │   Status: {status}   │   Action authorized: {action_auth}{RESET}", self.width))
        self._emit()

        if self._recent_warnings:
            self._emit(f"  {FG_YELLOW}Last warnings:{RESET}")
            for w in self._recent_warnings[-5:]:
                self._emit(f"  {FG_ORANGE}  ⚑ {w[:self.width - 10]}{RESET}")
            self._emit()

        self._emit(f"  {FG_GREY}Total ops executed: 886  ·  Warnings emitted: {self._warning_count}  ·  Run: {self.run_id}{RESET}")
        self._emit(self._rule("═", gate_col))
        self._emit()

    # ── Between-run summary ───────────────────────────────────────────────────

    def print_next_test_banner(self, next_test_name: str, reason: str,
                               run_num: int, total: Optional[int] = None):
        total_str = f"/{total}" if total else "/ ∞"
        self._emit()
        self._emit(self._rule("·", FG_BLUE))
        self._emit(f"  {FG_BLUE}AUTO-GENERATING NEXT TEST  [{run_num}{total_str}]{RESET}")
        self._emit(f"  {FG_GREY}Reason: {reason}{RESET}")
        self._emit(f"  {FG_WHITE}Next: {FG_CYAN}{next_test_name}{RESET}")
        self._emit(self._rule("·", FG_BLUE))
        self._emit()
