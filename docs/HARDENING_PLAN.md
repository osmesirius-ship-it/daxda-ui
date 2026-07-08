# DAXDA Stress-Test 04 — Engine Hardening

## Summary

The analysis identified 5 structural defects in the DAXDA audit engine that prevent it from correctly handling the replay-consistency and state-contamination stress tests. All 5 are fixable in the existing Python engine without changing the tile architecture. The Node.js stress-runner is not the authoritative audit system — the Python engine (`daxda-engine/`) is. We fix the Python engine and add a proper stress-test runner that invokes it.

---

## Problems Being Fixed

| # | Problem | Location | Severity |
|---|---------|----------|----------|
| 1 | **Hardcoded metrics** — `extractMetrics()` ignores source packet | JS runner only | Medium |
| 2 | **Source-ID-dependent gates** — `sources.A4` breaks on reorder | `tile_logic.py` + new module | **Critical** |
| 3 | **Unbounded run parsing** — Run A absorbs Run B/C text | New parser module | **Critical** |
| 4 | **Audit signature not verifiable** — RSA key discarded each run | `audit.py` | High |
| 5 | **No separation: audit_state vs action_state** | `engine.py` | High |

---

## Proposed Changes

### 1. New: `daxda-engine/core/source_classifier.py` [NEW]

Classification-based source analysis — the core fix for Problem 2.

```
classify_source(text) → SourceClassification
  • verified_telemetry
  • verified_financial_record
  • legal_or_procurement_control
  • operational_evidence
  • vendor_assertion
  • adversarial_contamination
  • unverifiable_provenance
  • verified_provenance_failure

extract_metrics_from_sources(classified_sources) → MetricBundle
  Parses numbers from source text:
  - correct_recommendations (regex: "Correct recommendations: N")
  - incorrect_adverse (regex: "Incorrect adverse recommendations: N")
  - incorrect_favorable (regex: "Incorrect favorable: N")
  - total_cases (regex: "Evaluation set: N")
  - cost_components (dollar amounts)
  - procurement_cap (dollar amounts in procurement sources)

evaluate_gates(classified_sources, metrics) → GateReport
  Gates use classification, NOT source IDs:
  - evidence_sufficiency: requires ≥1 verified_telemetry
  - financial_reconciliation: cost vs cap from financial+procurement sources
  - safety_review: incorrect_adverse_rate < threshold
  - legal_readiness: no legal_or_procurement_control with "no finalized"
  - instruction_integrity: no adversarial_contamination
  - provenance_integrity: no verified_provenance_failure
```

---

### 2. New: `daxda-engine/core/run_parser.py` [NEW]

Bounded run parser — fixes Problem 3.

```
parse_runs(raw_text) → dict[str, str]
  Splits on "# RUN A", "# RUN B", "# RUN C"
  Each run bounded to its section only — stops at next "# RUN" or "# REQUIRED OUTPUT"
  Returns {"RUN_A": "...", "RUN_B": "...", "RUN_C": "..."}

parse_sources_from_run(run_text) → list[Source]
  Extracts each [Source X — label] block
  Returns Source(id, label, text) without ID contaminating classification
```

---

### 3. Modify: `daxda-engine/core/audit.py` [MODIFY]

Fixes Problem 4 — persistent HMAC signing key, verifiable signature.

Changes:
- `compute_hash()` already uses HMAC with `DAXDA_SIGNING_KEY` env var — this is correct
- Add `verify_signature(audit_hash, audit_signature) → bool` function
- Add `build_canonical_payload(audit_dict) → dict` that strips non-deterministic fields (run timestamps, UUIDs) before hashing — for reproducibility

> [!NOTE]
> The current code uses `hmac.new` which is a bug — should be `hmac.new` → `hmac.new` is not a valid call. Should be `hmac.HMAC(key, msg, digest)`. This will be fixed.

---

### 4. Modify: `daxda-engine/core/engine.py` [MODIFY]

Fixes Problem 5 — explicit `audit_state` vs `action_state` separation.

Changes:
- `FinalDecision` gets `action_release_authorized: bool` field — distinct from `release_lock`
- `action_release_authorized` is only `True` when ALL of: status=GOVERNED, release_lock=CLEARED, final_gate=RELEASE
- Add `get_action_state()` helper that returns a safe summary with no trace data
- Comments make explicit: completing audit ≠ approving action

---

### 5. New: `daxda-engine/test_daxda_integration_hardened.py` [NEW]

Replaces the prototype JS runner with a proper Python integration test.

```python
Tests:
  test_run_parser_bounded()           — Run A does not absorb Run B text
  test_source_classification_by_type() — Legal review classified same regardless of ID
  test_metrics_extracted_from_text()  — Numbers come from source text, not hardcoded
  test_gate_replay_consistency()      — Run A and Run B gates match
  test_instruction_integrity_runC()   — Run C adversarial sources trigger FAIL
  test_provenance_failure_runC()      — Run C unverifiable manifest triggers FAIL
  test_audit_action_separation()      — audit_complete != action_released
  test_fail_closed_on_gate_fail()     — any gate FAIL → BLOCKED
  test_canonical_hash_deterministic() — same input → same canonical hash
  test_hmac_signature_verifiable()    — signature can be verified with known key
```

---

### 6. New: `daxda-engine/test_daxda_safety_critical.py` [NEW]

Unit tests for the lower-level components.

```python
Tests:
  test_canonical_hash_strips_timestamps()
  test_canonical_hash_strips_run_ids()  
  test_audit_complete_not_action_released()
  test_fail_closed_when_model_unavailable()
  test_air_gap_blocks_socket_calls()
  test_run_A_B_gate_agreement()
  test_run_C_contamination_detected()
  test_provenance_failure_is_release_blocker()
```

---

## Verification Plan

### Automated Tests
```bash
cd daxda-engine
python3 -m pytest test_daxda_integration_hardened.py test_daxda_safety_critical.py -v
```

**Expected: 29+ tests pass**

### Gate Correctness Table (what the tests enforce)

| Gate | Run A | Run B | Run C |
|------|-------|-------|-------|
| Evidence sufficiency | PASS | PASS | PASS |
| Financial reconciliation | FAIL | FAIL | FAIL |
| Safety review | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| Legal readiness | FAIL | FAIL | FAIL |
| Instruction integrity | PASS | PASS | **FAIL** |
| Provenance integrity | INCOMPLETE | INCOMPLETE | **FAIL** |
| Final authority | BLOCKED | BLOCKED | BLOCKED |

Run A = Run B (replay consistency) ✓  
Run C adds contamination on top ✓

---

## Open Questions

> [!IMPORTANT]
> **Q: Should the JS stress-runner (`Pasted text(23).txt`) be replaced, updated, or deprecated?**
> It is currently standalone. The Python engine is authoritative. The JS runner is useful for demos but has the hardcoded-metrics problem. Options:
> - Keep JS as a demo shell that calls the Python API
> - Delete JS runner
> - Fix JS runner to extract metrics from text

> [!NOTE]
> **Q: Persistent signing key storage** — for now the HMAC key lives in `DAXDA_SIGNING_KEY` env var. For production this should be a key file with rotation policy. Not blocking this PR but noted.
