"""
DAXDA.IA — 886-Ops Runtime Engine
Nicole Protocol / 886-Ops Architecture

Implements the minimal runtime pseudocode from Section 13:

    def run_daxda_886(input_payload):
        state = initialize_state(input_payload)
        for layer in LAYERS_16:
            for tile in layer.tiles_55:
                result = tile.execute(state)
                state = apply_tile_result(state, result)
                state.audit.append(result.trace_entry)
                if result.gate == 'BLOCK':
                    return blocked_output(state)
                if result.gate == 'RECURSE':
                    state = run_targeted_recursion(state, result.recursion_payload)
        state = run_post_layer_system_ops(state)
        return governed_output(state)

Post-layer system operations (SYS_881–SYS_886):
  SYS_881 — Final scoring
  SYS_882 — Authority assignment
  SYS_883 — Audit manifest build
  SYS_884 — Release lock evaluation
  SYS_885 — Re-entry hook registration
  SYS_886 — Memory boundary commit
"""
from __future__ import annotations
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
import requests
import json
from .discovery import initiate_discovery, process_discovery

def generate_layer_amalgamation(layer_id: str, layer_name: str, layer_trace: list, active_input: str, api_url: str, api_key: str) -> str:
    prompt = f"You are DAXDA's {layer_id} ({layer_name}) layer. Your job is to analyze and explain the layer's execution. \n"
    prompt += "Provide a detailed textual reasoning (an amalgamation of your thoughts) explaining the evaluations, warnings, and notes generated during this layer's execution. Do not use JSON.\n"
    prompt += f"User Input: {active_input}\n"
    prompt += f"Trace entries for this layer:\n"
    for t in layer_trace:
        prompt += f"- {t.get('function_name', 'unknown')} (Gate: {t.get('gate', 'unknown')}): {t.get('notes', '')}\n"
        for w in t.get('warnings', []):
            prompt += f"  - WARNING: {w}\n"
            
    if not api_url:
        api_url = "http://127.0.0.1:11434/v1"
        api_key = "ollama"

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": "mistral-large", "messages": [{"role": "user", "content": prompt}]}
    
    try:
        res = requests.post(f"{api_url.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=10)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Fallback layer amalgamation due to error: {e}"

from .audit import AuditManifest, build_trace_entry_dict
from .gates import GateState
from .layers import Layer, build_layer_registry
from .recursion import RecursionState
from .scoring import FourScoreCard, ScoreVector
from .tiles import TileInput

RULE_PACK_VERSION = "886-ops-v1.3"  # bump when tile logic changes


# Runtime mode operation budgets
RUNTIME_MODES = {
    "quick":    128,
    "standard": 512,
    "full_886": 886,
}


@dataclass
class EngineState:
    run_id: str
    active_input: str
    runtime_mode: str
    caller_intent: str = "decision_request"
    input_hash: str = ""                    # SHA-256 of raw input for provenance
    score: ScoreVector = field(default_factory=ScoreVector)
    four_scores: FourScoreCard = field(default_factory=FourScoreCard)
    warnings: list[str] = field(default_factory=list)
    unique_warning_keys: set = field(default_factory=set)   # for dedup
    trace: list[dict] = field(default_factory=list)
    layer_outputs: list[dict] = field(default_factory=list)
    recursion: RecursionState = field(default_factory=RecursionState)
    tiles_executed: int = 0
    layers_executed: int = 0
    blocked_at: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    evidence_state: dict = field(default_factory=dict)
    upstream_state: dict = field(default_factory=dict)
    llm_anomalies: list[dict] = field(default_factory=list)
    authority_level: str = "ADVISORY"
    semantic_state: dict = field(default_factory=dict)


@dataclass
class FinalDecision:
    run_id: str
    caller_intent: str
    workflow_type: str
    final_gate: GateState
    final_stability_score: float
    authority_level: str
    release_lock: str  # "CLEARED" | "HELD"
    canonical_input_hash: str
    canonical_output_hash: str
    status: str
    warnings: list[str] = field(default_factory=list)
    blocked_at: Optional[str] = None
    four_scores: dict = field(default_factory=dict)

    # ── Audit / Action separation (Problem 5 fix) ─────────────────────────────
    # Completing the audit trace does NOT authorize action release.
    # action_release_authorized requires ALL of:
    #   status == "GOVERNED"
    #   release_lock == "CLEARED"
    #   final_gate == GateState.RELEASE
    #   no hard gate failures
    # Everything else is audit-only: useful for evidence, not a green light.
    audit_complete: bool = False
    action_release_authorized: bool = False

    def __post_init__(self):
        self.audit_complete = self.status in ("GOVERNED", "BLOCKED", "CONVERSATIONAL",
                                              "CLASSIFICATION_CONFLICT")
        self.action_release_authorized = (
            self.status == "GOVERNED"
            and self.release_lock == "CLEARED"
            and self.final_gate == GateState.RELEASE
            and self.authority_level == "AUTHORITATIVE"
        )

    def get_action_state(self) -> dict:
        """Return the action-release state — safe to expose externally.
        Contains no trace data, no warnings detail, no score internals."""
        return {
            "audit_complete": self.audit_complete,
            "action_release_authorized": self.action_release_authorized,
            "authority_level": self.authority_level,
            "release_lock": self.release_lock,
            "final_gate": str(self.final_gate),
            # Explicit note so no caller can confuse these two states:
            "NOTE": (
                "audit_complete=True does NOT mean action_release_authorized=True. "
                "Action release requires all gates clear and authority AUTHORITATIVE."
            ),
        }

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "caller_intent": self.caller_intent,
            "workflow_type": self.workflow_type,
            "final_gate": self.final_gate,
            "final_stability_score": self.final_stability_score,
            "authority_level": self.authority_level,
            "release_lock": self.release_lock,
            "canonical_input_hash": self.canonical_input_hash,
            "canonical_output_hash": self.canonical_output_hash,
            "status": self.status,
            "warnings": self.warnings,
            "blocked_at": self.blocked_at,
            "four_scores": self.four_scores,
            "audit_complete": self.audit_complete,
            "action_release_authorized": self.action_release_authorized,
        }


def initialize_state(active_input: str, runtime_mode: str = "full_886", caller_intent: str = "decision_request") -> EngineState:
    input_hash = hashlib.sha256(active_input.encode()).hexdigest()[:16]
    four_card = FourScoreCard()
    four_card.caller_intent = caller_intent
    return EngineState(
        run_id=str(uuid.uuid4()),
        active_input=active_input,
        runtime_mode=runtime_mode,
        caller_intent=caller_intent,
        input_hash=input_hash,
        score=ScoreVector(),
        four_scores=four_card,
        started_at=time.time(),
    )


def compute_canonical_decision(state: EngineState) -> FinalDecision:
    four = state.four_scores
    four.unique_findings = len(set(
        (w.split("]")[-1].strip() if "]" in w else w) for w in state.warnings
    ))
    four.total_warnings = len(state.warnings)
    four.compute_readiness()

    threshold = 0.80
    final_score = state.score.total_stability()

    # Rule 4: If any hard gate is BLOCK, FINAL_GATE cannot be PASS or RELEASE.
    any_hard_block = (
        state.blocked_at is not None or
        any(t.get("gate") == GateState.BLOCK or (t.get("notes") and "No implementation" in str(t.get("notes"))) for t in state.trace) or
        four.decision_readiness < 0.20 or
        (four.evidence_applicable and four.evidence_sufficiency < 0.50) or
        four.input_threat > 0.0
    )

    # Rule 3: Check for classification conflict with caller intent
    has_conflict = any("CLASSIFICATION_CONFLICT" in w for w in state.warnings) or (
        state.caller_intent in ("audit", "stress_test", "decision_request") and four.workflow_type == "conversational"
    )

    if has_conflict:
        status = "CLASSIFICATION_CONFLICT"
        final_gate = GateState.DEFERRED
        authority_level = "DEFERRED"
        release_lock = "HELD"
    elif four.workflow_type == "conversational":
        status = "CONVERSATIONAL"
        final_gate = GateState.PASS
        authority_level = "not requested"
        release_lock = "CLEARED"
    elif any_hard_block:
        status = "BLOCKED"
        final_gate = GateState.BLOCK
        release_lock = "HELD"
        if not four.evidence_applicable or four.evidence_sufficiency < 0.50:
            authority_level = "BLOCKED"
        elif four.input_threat > 0.0:
            authority_level = "BLOCKED"
        elif four.output_integrity < threshold:
            authority_level = "PUBLISH_BLOCK"
        else:
            authority_level = "BLOCKED"
    else:
        status = "GOVERNED"
        if four.output_integrity < threshold:
            final_gate = GateState.BLOCK
            authority_level = "PUBLISH_BLOCK"
            release_lock = "HELD"
        elif four.decision_readiness >= threshold and final_score >= 0.80:
            final_gate = GateState.RELEASE
            authority_level = "AUTHORITATIVE"
            release_lock = "CLEARED"
        elif four.decision_readiness >= 0.50:
            final_gate = GateState.CAUTION
            authority_level = "ADVISORY"
            release_lock = "HELD"
        else:
            final_gate = GateState.BLOCK
            authority_level = "BLOCKED"
            release_lock = "HELD"

    # Rule 5: Compute canonical output hash
    output_payload = json.dumps({
        "run_id": state.run_id,
        "final_gate": str(final_gate),
        "final_stability_score": round(four.decision_readiness if four.workflow_type != "conversational" else 1.0, 4),
        "authority_level": authority_level,
        "release_lock": release_lock,
        "status": status
    }, sort_keys=True)
    canonical_output_hash = hashlib.sha256(output_payload.encode()).hexdigest()[:16]

    return FinalDecision(
        run_id=state.run_id,
        caller_intent=state.caller_intent,
        workflow_type=four.workflow_type,
        final_gate=final_gate,
        final_stability_score=round(four.decision_readiness if four.workflow_type != "conversational" else 1.0, 4),
        authority_level=authority_level,
        release_lock=release_lock,
        canonical_input_hash=state.input_hash,
        canonical_output_hash=canonical_output_hash,
        status=status,
        warnings=state.warnings,
        blocked_at=state.blocked_at,
        four_scores=four.to_dict()
    )


def apply_tile_result(state: EngineState, result) -> EngineState:
    state.score = state.score.apply_delta(result.legacy_delta)
    state.four_scores.apply_four_score_delta(result.score_delta)
    state.warnings.extend(result.warning_delta)
    result.trace_entry.score_after = state.four_scores.to_dict()
    state.trace.append(build_trace_entry_dict(result.trace_entry))
    state.tiles_executed += 1
    return state


def run_targeted_recursion(state: EngineState, payload: dict, layers: list[Layer]) -> EngineState:
    target_layer_id = payload.get("layer_id")
    if not state.recursion.can_recurse(target_layer_id):
        state.warnings.append(
            f"RECURSION_EXHAUSTED: Cannot re-enter {target_layer_id} — depth limit reached."
        )
        return state

    state.recursion.record_recursion(target_layer_id, payload)

    target_layer = next((l for l in layers if l.layer_id == target_layer_id), None)
    if not target_layer:
        state.warnings.append(f"RECURSION_ERROR: Layer {target_layer_id} not found.")
        return state

    tile_input = TileInput(
        active_input=state.active_input,
        upstream_state=state.upstream_state,
        layer_context={"recursion": True, "payload": payload},
        evidence_state=state.evidence_state,
    )

    for tile in target_layer.tiles:
        result = tile.execute(tile_input, state.score, state.four_scores)
        state = apply_tile_result(state, result)
        if result.gate == GateState.BLOCK:
            state.blocked_at = f"RECURSION:{tile.tile_id}"
            return state

    return state


def run_post_layer_system_ops(state: EngineState) -> EngineState:
    """
    SYS_881–SYS_886: Final scoring, authority, manifest, release lock, re-entry, memory boundary.
    Each op performs real work and emits a trace entry.
    """
    decision = compute_canonical_decision(state)
    state.authority_level = decision.authority_level
    final_score = decision.final_stability_score

    # SYS_881 — Final Scoring
    state.trace.append({
        "tile_id": "SYS_881",
        "function_name": "final_scoring",
        "layer_id": "SYSTEM",
        "gate": GateState.PASS,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": [],
        "notes": f"Final TOTAL_STABILITY computed: {round(final_score, 4)}. Logic={round(state.score.logic,3)}, Assumption={round(state.score.assumption_integrity,3)}.",
    })
    state.tiles_executed += 1

    # SYS_882 — Authority Assignment
    authority = decision.authority_level
    state.trace.append({
        "tile_id": "SYS_882",
        "function_name": "authority_assignment",
        "layer_id": "SYSTEM",
        "gate": GateState.PASS if authority != "BLOCKED" else GateState.BLOCK,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": [f"Authority restricted to {authority}"] if authority in ("ADVISORY", "BLOCKED", "DEFERRED") else [],
        "notes": f"Authority assigned: {authority}. Status: {decision.status}.",
    })
    state.tiles_executed += 1

    # SYS_883 — Audit Manifest Build
    manifest_hash = decision.canonical_output_hash
    state.trace.append({
        "tile_id": "SYS_883",
        "function_name": "audit_manifest_build",
        "layer_id": "SYSTEM",
        "gate": GateState.PASS,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": [],
        "notes": f"Audit manifest built. Trace entries={len(state.trace)}, canonical_output_hash={manifest_hash}.",
    })
    state.tiles_executed += 1

    # SYS_884 — Release Lock Evaluation
    base_tile_count = state.tiles_executed
    unique_warnings = len(set(
        (w.split("]")[-1].strip() if "]" in w else w) for w in state.warnings
    ))
    unique_warning_rate = unique_warnings / max(1, base_tile_count)
    total_warning_rate  = len(state.warnings) / max(1, base_tile_count)
    release_ok = (decision.release_lock == "CLEARED")
    release_gate = decision.final_gate
    release_warnings = []
    if not release_ok:
        release_warnings.append(f"Release lock HELD. Status: {decision.status}, Final Gate: {decision.final_gate}.")
    state.trace.append({
        "tile_id": "SYS_884",
        "function_name": "release_lock_evaluation",
        "layer_id": "SYSTEM",
        "gate": release_gate,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": release_warnings,
        "notes": (
            f"Release lock: {decision.release_lock}. "
            f"Unique warning rate={round(unique_warning_rate,3)} "
            f"(total={round(total_warning_rate,3)}, "
            f"denominator={base_tile_count} tiles)."
        ),
        "provenance": {
            "run_id": state.run_id,
            "input_hash": state.input_hash,
            "canonical_output_hash": decision.canonical_output_hash,
            "rule_pack_version": RULE_PACK_VERSION,
        },
    })
    state.warnings.extend(release_warnings)
    state.tiles_executed += 1

    # SYS_885 — Re-entry Hook Registration
    needs_reentry = final_score < 0.75 or len(state.warnings) > 5 or decision.final_gate in (GateState.RECURSE, GateState.DEFERRED)
    hooks = []
    if needs_reentry:
        hooks.append(f"reentry::score_below_threshold::{round(final_score,4)}")
    if state.recursion.depth > 0:
        hooks.append(f"reentry::recursion_depth::{state.recursion.depth}")
    state.trace.append({
        "tile_id": "SYS_885",
        "function_name": "reentry_hook_registration",
        "layer_id": "SYSTEM",
        "gate": GateState.PASS,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": [],
        "notes": f"Re-entry hooks registered: {len(hooks)}. {', '.join(hooks) if hooks else 'No re-entry required.'}",
    })
    state.tiles_executed += 1

    # SYS_886 — Memory Boundary Commit
    retained = ["run_id", "final_gate", "final_stability_score", "authority_level", "release_lock", "canonical_output_hash", "warnings"]
    discarded = ["intermediate_tile_results", "raw_score_deltas"]
    archived = ["trace", "audit_manifest"]
    state.trace.append({
        "tile_id": "SYS_886",
        "function_name": "memory_boundary_commit",
        "layer_id": "SYSTEM",
        "gate": GateState.PASS,
        "score_before": round(final_score, 4),
        "score_after": round(final_score, 4),
        "warnings": [],
        "notes": f"Memory boundary committed. Retained={retained}. Archived={archived}. Discarded={discarded}.",
    })
    state.tiles_executed += 1

    return state




def governed_output(state: EngineState) -> dict:
    decision = compute_canonical_decision(state)
    state.authority_level = decision.authority_level
    four = state.four_scores

    manifest = AuditManifest(
        run_id=state.run_id,
        canonical_input_hash=decision.canonical_input_hash,
        canonical_output_hash=decision.canonical_output_hash,
        model_id="daxda-engine",
        model_version="1.0.0",
        temperature=0.0,
        seed="N/A",
        parent_run_id="none",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        input_snapshot=state.active_input[:500],
        runtime_mode=state.runtime_mode,
        total_operations=state.tiles_executed,
        layers_executed=state.layers_executed,
        tiles_executed=state.tiles_executed,
        final_gate=decision.final_gate,
        final_stability_score=decision.final_stability_score,
        warnings=state.warnings,
        recursion_depth=state.recursion.depth,
        trace=state.trace,
        blocked_at=state.blocked_at,
        started_at=state.started_at,
        completed_at=time.time(),
    )
    manifest_dict = manifest.to_dict()
    semantic_state = getattr(state, "semantic_state", {})
    manifest_dict["semantic_state"] = semantic_state
    manifest_dict["layer_outputs"] = state.layer_outputs

    return {
        "run_id": state.run_id,
        "input_hash": state.input_hash,
        "rule_pack_version": RULE_PACK_VERSION,
        "runtime_mode": state.runtime_mode,
        "final_gate": decision.final_gate,
        "final_stability_score": decision.final_stability_score,
        "authority_level": decision.authority_level,
        "release_lock": decision.release_lock,
        "status": decision.status,
        "canonical_output_hash": decision.canonical_output_hash,
        "final_decision": decision.to_dict(),
        "four_scores": decision.four_scores,
        "warning_count": len(state.warnings),
        "unique_warning_count": four.unique_findings,
        "recursive_recurrence_count": len(state.warnings) - four.unique_findings,
        "warnings": state.warnings,
        "tiles_executed": state.tiles_executed,
        "layers_executed": state.layers_executed,
        "recursion_depth": state.recursion.depth,
        "blocked_at": state.blocked_at,
        "audit_manifest": manifest_dict,
        "semantic_state": semantic_state,
    }



def blocked_output(state: EngineState, blocked_at: str) -> dict:
    state.blocked_at = blocked_at
    decision = compute_canonical_decision(state)
    four = state.four_scores

    manifest = AuditManifest(
        run_id=state.run_id,
        canonical_input_hash=decision.canonical_input_hash,
        canonical_output_hash=decision.canonical_output_hash,
        model_id="daxda-engine",
        model_version="1.0.0",
        temperature=0.0,
        seed="N/A",
        parent_run_id="none",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        input_snapshot=state.active_input[:500],
        runtime_mode=state.runtime_mode,
        total_operations=state.tiles_executed,
        layers_executed=state.layers_executed,
        tiles_executed=state.tiles_executed,
        final_gate=decision.final_gate,
        final_stability_score=decision.final_stability_score,
        warnings=state.warnings,
        recursion_depth=state.recursion.depth,
        trace=state.trace,
        blocked_at=blocked_at,
        started_at=state.started_at,
        completed_at=time.time(),
    )
    manifest_dict = manifest.to_dict()
    semantic_state = getattr(state, "semantic_state", {})
    manifest_dict["semantic_state"] = semantic_state
    manifest_dict["layer_outputs"] = state.layer_outputs

    return {
        "run_id": state.run_id,
        "input_hash": state.input_hash,
        "rule_pack_version": RULE_PACK_VERSION,
        "runtime_mode": state.runtime_mode,
        "final_gate": decision.final_gate,
        "final_stability_score": decision.final_stability_score,
        "authority_level": decision.authority_level,
        "release_lock": decision.release_lock,
        "status": decision.status,
        "canonical_output_hash": decision.canonical_output_hash,
        "final_decision": decision.to_dict(),
        "four_scores": decision.four_scores,
        "warning_count": len(state.warnings),
        "unique_warning_count": four.unique_findings,
        "recursive_recurrence_count": len(state.warnings) - four.unique_findings,
        "warnings": state.warnings,
        "tiles_executed": state.tiles_executed,
        "layers_executed": state.layers_executed,
        "recursion_depth": state.recursion.depth,
        "blocked_at": blocked_at,
        "audit_manifest": manifest_dict,
        "semantic_state": semantic_state,
    }


def run_daxda_886(active_input: str, runtime_mode: str = "full_886", forge_api_url: str = None, forge_api_key: str = None, caller_intent: str = "decision_request") -> dict:
    """
    Main entry point for the DAXDA 886-Ops runtime.
    Executes all 16 layers × 55 tiles + 6 post-layer system ops = 886 total operations.
    """
    from .cognitive_ensemble import run_cognitive_ensemble
    layers = build_layer_registry()
    state = initialize_state(active_input, runtime_mode, caller_intent)
    
    semantic_state = {}
    if runtime_mode == "full_886":
        ensemble_result = run_cognitive_ensemble(active_input, forge_api_url, forge_api_key)
        semantic_state = ensemble_result
        state.semantic_state = semantic_state
        
        exec_synthesis = ensemble_result.get("executive_synthesis", {})
        self_assess = ensemble_result.get("streams", {}).get("self_assessment", {})
        
        # Parse LM contradictions and inconsistencies to trigger the DAXDA penalty box
        anomalies = []
        for c in exec_synthesis.get("contradictions_found", []):
            anomalies.append({
                "layer_id": "CON_1", 
                "tile_id": "contradiction_probe", 
                "gate": "BLOCK", 
                "notes": c,
                "provenance": exec_synthesis.get("llm_provenance", {})
            })
        for inc in self_assess.get("inconsistencies", []):
            anomalies.append({
                "layer_id": "TRC_1", 
                "tile_id": "logic_validity_check", 
                "gate": "WARN", 
                "notes": inc,
                "provenance": self_assess.get("llm_provenance", {})
            })
            
        state.llm_anomalies = anomalies 
        state.score.logic_score = self_assess.get("confidence", 0.9)

    tile_input = TileInput(
        active_input=active_input,
        upstream_state={},
        layer_context={},
        evidence_state={},
        semantic_state=semantic_state,
        llm_anomalies=state.llm_anomalies,
        caller_intent=state.caller_intent,
        runtime_mode=state.runtime_mode,
    )

    for layer in layers:
        layer_start_score = state.score.total_stability()

        for tile in layer.tiles:
            tile_input.upstream_state = state.upstream_state
            result = tile.execute(tile_input, state.score, state.four_scores)
            state = apply_tile_result(state, result)

            if result.gate == GateState.BLOCK:
                # Initiate discovery instead of immediate termination
                state = initiate_discovery(state, blocked_tile_id=tile.tile_id, failure_result=result)
                # Continue processing; discovery may resolve the block
                continue

            if result.gate == GateState.RECURSE and result.recursion_payload:
                state = run_targeted_recursion(state, result.recursion_payload, layers)
                if state.blocked_at:
                    return blocked_output(state, blocked_at=state.blocked_at)

        state.layers_executed += 1
        
        layer_trace = [t for t in state.trace if t.get('layer_id') == layer.layer_id]
        if runtime_mode in ("quick", "dry_run", "strict_deterministic"):
            amalgamation = f"[{layer.layer_id} {layer.layer_name}] Amalgamation skipped in {runtime_mode} mode."
        else:
            amalgamation = generate_layer_amalgamation(layer.layer_id, layer.layer_name, layer_trace, active_input, forge_api_url, forge_api_key)
        
        state.layer_outputs.append({
            "layer_id": layer.layer_id,
            "layer_name": layer.layer_name,
            "score_at_exit": round(state.score.total_stability(), 4),
            "amalgamation": amalgamation,
        })

    if getattr(state, "discovery_needed", False):
        state = process_discovery(state)
    state = run_post_layer_system_ops(state)
    return governed_output(state)
