"""
DAXDA Sandbox — Trace Player
Replays 886 trace entries in real time at a configurable speed.
Groups entries by layer, fires display callbacks on each tile.
"""
from __future__ import annotations
import time
from typing import Callable, Optional
from .display import SandboxDisplay, _gate_str


def play_trace(
    trace: list[dict],
    display: SandboxDisplay,
    delay_ms: float = 12.0,
    score_ticker_every: int = 55,
) -> None:
    """
    Stream all 886 trace entries through the display at `delay_ms` per op.

    Args:
        trace:              The 886-entry list from audit_manifest.trace
        display:            SandboxDisplay instance to render into
        delay_ms:           Milliseconds to sleep between each tile render
        score_ticker_every: Print a score snapshot every N ops
    """
    delay_s = delay_ms / 1000.0

    # Separate system ops from tile ops
    tile_ops   = [e for e in trace if not str(e.get("tile_id", "")).startswith("SYS_")]
    system_ops = [e for e in trace if str(e.get("tile_id", "")).startswith("SYS_")]

    # Group tile ops by layer
    layers: dict[str, list[dict]] = {}
    layer_order: list[str] = []
    for entry in tile_ops:
        lid = entry.get("layer_id", "UNKNOWN")
        if lid not in layers:
            layers[lid] = []
            layer_order.append(lid)
        layers[lid].append(entry)

    abs_op = 0

    # ── Play layers ──────────────────────────────────────────────────────────
    for layer_num, layer_id in enumerate(layer_order, start=1):
        entries = layers[layer_id]
        display.print_layer_start(layer_id, layer_num)

        for tile_idx, entry in enumerate(entries, start=1):
            abs_op += 1
            display.print_tile(entry, tile_idx, abs_op)

            if abs_op % score_ticker_every == 0:
                display.print_score_ticker(abs_op)

            if delay_s > 0:
                time.sleep(delay_s)

    # ── System ops ───────────────────────────────────────────────────────────
    if system_ops:
        display.print_layer_start("SYSTEM", 17)
        for i, entry in enumerate(system_ops, start=1):
            abs_op += 1
            display.print_system_op(entry, i)
            if delay_s > 0:
                time.sleep(delay_s)

    display.print_score_ticker(abs_op)
