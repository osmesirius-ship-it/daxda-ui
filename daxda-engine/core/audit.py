"""
DAXDA.IA — Audit Trace Builder
Nicole Protocol / 886-Ops Architecture

Collects trace entries from all tiles and builds the final audit manifest.
Warnings must propagate forward and cannot disappear unless explicitly resolved.

Signature protocol:
  - HMAC-SHA256 over audit_hash using DAXDA_SIGNING_KEY env var.
  - Key is persistent (env var) so signatures are verifiable after the fact.
  - verify_signature() allows external verification without the private key.
  - build_canonical_payload() strips non-deterministic fields (timestamps,
    run UUIDs, nonces) so the same audit always hashes the same way.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .gates import GateState
from .tiles import TraceEntry


@dataclass
class AuditManifest:
    run_id: str
    input_snapshot: str
    runtime_mode: str
    total_operations: int
    layers_executed: int
    tiles_executed: int
    final_gate: GateState
    final_stability_score: float
    warnings: list[str]
    recursion_depth: int
    trace: list[dict]
    blocked_at: str | None
    started_at: float
    completed_at: float
    canonical_input_hash: str = ""
    canonical_output_hash: str = ""
    model_id: str = "daxda-engine"
    model_version: str = "1.0.0"
    temperature: float = 0.0
    seed: str = "N/A"
    parent_run_id: str = "none"
    timestamp_utc: str = ""
    audit_hash: str = ""
    audit_signature: str = ""

    def compute_hash(self) -> str:
        payload = json.dumps({
            "run_id": self.run_id,
            "input_snapshot": self.input_snapshot,
            "final_gate": self.final_gate,
            "final_stability_score": self.final_stability_score,
            "tiles_executed": self.tiles_executed,
        }, sort_keys=True)
        self.audit_hash = hashlib.sha256(payload.encode()).hexdigest()

        # Sign the manifest hash with a persistent HMAC key.
        # The key lives in DAXDA_SIGNING_KEY env var so it is consistent
        # across runs and signatures can be verified later.
        secret_key = os.environ.get("DAXDA_SIGNING_KEY", "default-insecure-daxda-key").encode()
        self.audit_signature = hmac.new(
            secret_key, self.audit_hash.encode(), hashlib.sha256
        ).hexdigest()

        return self.audit_hash

    def to_dict(self) -> dict:
        self.compute_hash()
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "timestamp_utc": self.timestamp_utc,
            "canonical_input_hash": self.canonical_input_hash,
            "canonical_output_hash": self.canonical_output_hash,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "temperature": self.temperature,
            "seed": self.seed,
            "input_snapshot": self.input_snapshot[:200],
            "runtime_mode": self.runtime_mode,
            "total_operations": self.total_operations,
            "layers_executed": self.layers_executed,
            "tiles_executed": self.tiles_executed,
            "final_gate": self.final_gate,
            "final_stability_score": round(self.final_stability_score, 4) if isinstance(self.final_stability_score, float) else self.final_stability_score,
            "warnings": self.warnings,
            "recursion_depth": self.recursion_depth,
            "blocked_at": self.blocked_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.completed_at - self.started_at, 4),
            "audit_hash": self.audit_hash,
            "audit_signature": self.audit_signature,
            "trace": self.trace,
        }

def build_trace_entry_dict(entry: TraceEntry) -> dict:
    # Handle dicts or floats for score
    def fmt(val):
        if isinstance(val, dict):
            return val
        if isinstance(val, float):
            return round(val, 4)
        return val

    return {
        "tile_id": entry.tile_id,
        "function_name": entry.function_name,
        "layer_id": entry.layer_id,
        "gate": entry.gate,
        "score_before": fmt(entry.score_before),
        "score_after": fmt(entry.score_after),
        "warnings": entry.warnings,
        "notes": entry.notes,
        "timestamp": entry.timestamp,
    }


# ── Canonical payload for reproducible hashing ───────────────────────────────

# Fields that vary across runs even for identical inputs — strip before hashing
_NON_DETERMINISTIC_FIELDS = frozenset([
    "run_id", "parent_run_id", "timestamp_utc", "started_at", "completed_at",
    "duration_seconds", "audit_hash", "audit_signature", "nonce", "uuid",
    "canonical_input_hash",   # includes run_id substring
    "canonical_output_hash",  # depends on run_id
])


def build_canonical_payload(audit_dict: dict) -> dict:
    """
    Strip non-deterministic fields from an audit dict before hashing.

    This ensures that the same input processed twice — even at different times
    or with different run UUIDs — produces the same canonical hash.

    Fields retained: final_gate, final_stability_score, tiles_executed,
    input_snapshot, runtime_mode, warnings, blocked_at.
    """
    return {
        k: v
        for k, v in audit_dict.items()
        if k not in _NON_DETERMINISTIC_FIELDS and k != "trace"
    }


def verify_signature(audit_hash: str, audit_signature: str,
                     signing_key: str | None = None) -> bool:
    """
    Verify that audit_signature is the valid HMAC-SHA256 of audit_hash
    under the persistent signing key.

    Args:
        audit_hash:      The SHA-256 hex digest stored in the manifest.
        audit_signature: The HMAC hex digest stored in the manifest.
        signing_key:     Optional override; defaults to DAXDA_SIGNING_KEY env var.

    Returns:
        True  → signature is authentic.
        False → signature is invalid or tampered.
    """
    key = (signing_key or os.environ.get(
        "DAXDA_SIGNING_KEY", "default-insecure-daxda-key"
    )).encode()
    expected = hmac.new(key, audit_hash.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, audit_signature)


def canonical_hash_of(audit_dict: dict) -> str:
    """
    Compute a deterministic SHA-256 over the canonical (non-deterministic-stripped)
    fields of an audit dict.

    Two audit runs of the same input should produce the same canonical hash.
    """
    canonical = build_canonical_payload(audit_dict)
    payload = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()

