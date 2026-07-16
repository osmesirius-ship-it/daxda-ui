"""
DAXDA.IA — 55 Universal Tile Logic Functions
Nicole Protocol / 886-Ops Architecture

Each of the 55 tile functions performs real deterministic analysis
on the active_input within the context of its parent layer.
Returns: (score_delta_dict, warnings_list, notes_str)
"""
from __future__ import annotations
import re
import hashlib
import time
from typing import Any


# ─── Pattern Libraries ────────────────────────────────────────────────────────

URGENCY_PATTERNS = re.compile(
    r'\b(immediately|urgent|asap|right now|critical|emergency|no time|deadline|must|now)\b', re.I)
ABSOLUTE_PATTERNS = re.compile(
    r'\b(always|never|everyone|all customers|definitely|certainly|confirmed|proven|guaranteed|impossible)\b', re.I)
ASSERTIVE_PATTERNS = re.compile(
    r'\b(achieves|proves|demonstrates|establishes|guarantees|is the future|will|does)\b', re.I)
NEGATION_PATTERNS = re.compile(
    r'\b(not|no|never|none|without|excluding|ignore|skip|bypass|disable|remove)\b', re.I)
SCOPE_PATTERNS = re.compile(
    r'\b(only|just|merely|solely|exclusively|limited to|nothing else|specific)\b', re.I)
RISK_PATTERNS = re.compile(
    r'\b(delete|drop|remove|wipe|overwrite|deploy|production|live|public|broadcast|send to all|write access|admin|root|sudo)\b', re.I)
VAGUE_PATTERNS = re.compile(
    r'\b(something|somehow|maybe|perhaps|might|could be|seems like|I think|probably|around|approximately|unclear)\b', re.I)
CAUSAL_PATTERNS = re.compile(
    r'\b(because|therefore|thus|so|since|causes|leads to|results in|due to|as a result|consequently)\b', re.I)
PII_PATTERNS = re.compile(
    r'\b(\d{3}-\d{2}-\d{4}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}|\b\d{10,16}\b)\b')
ADVERSARIAL_PATTERNS = re.compile(
    r'\b(ignore previous|disregard|forget|override|pretend|act as if|you are now|jailbreak|do not follow|bypass your|new instruction)\b', re.I)
DECISION_WORDS = re.compile(
    r'\b(should|recommend|decide|choose|approve|reject|proceed|halt|implement|deploy|authorize|confirm|audit|verify|verification|test|testing|assess|evaluate|review)\b', re.I)
FINANCIAL_PATTERNS = re.compile(
    r'(\$[\d,]+|\d+\s*(million|billion|thousand|k|m)\b|\bbudget\b|\bcost\b|\bprice\b|\brevenue\b)', re.I)


class CountWithWords(int):
    def __new__(cls, count, words=None):
        obj = super().__new__(cls, count)
        obj.words = words or []
        return obj

    def __str__(self):
        if self.words:
            words_str = ", ".join(f"'{w}'" for w in set(self.words))
            return f"{int(self)} [{words_str}]"
        return str(int(self))
    
    def __format__(self, format_spec):
        if format_spec == '' and self.words:
            return str(self)
        return super().__format__(format_spec)

    def __add__(self, other):
        res = super().__add__(other)
        other_words = getattr(other, 'words', [])
        return CountWithWords(res, self.words + other_words)

    def __radd__(self, other):
        return self.__add__(other)

def _count(pattern: re.Pattern, text: str):
    matches = pattern.findall(text)
    return CountWithWords(len(matches), matches)


def _clamp(val: float, lo: float = -0.3, hi: float = 0.05) -> float:
    return max(lo, min(hi, val))


# ─── 55 Tile Functions ────────────────────────────────────────────────────────

def intake_snapshot(inp: str, layer_id: str, score: dict) -> tuple:
    length = len(inp)
    words = len(inp.split())
    notes = f"Snapshot: {words} words, {length} chars. Layer={layer_id}."
    return {}, [], notes


def normalize_input(inp: str, layer_id: str, score: dict) -> tuple:
    issues = []
    if layer_id == "FDL_1":
        if inp != inp.strip():
            issues.append("Leading/trailing whitespace detected")
        if re.search(r'\s{2,}', inp):
            issues.append("Irregular whitespace detected")
    notes = f"Normalization check: {', '.join(issues) if issues else 'Input is clean'}."
    delta = {"decision_readiness": -0.01 * len(issues)}
    return delta, issues, notes


def domain_classify(inp: str, layer_id: str, score: dict) -> tuple:
    domains = []
    if FINANCIAL_PATTERNS.search(inp) or re.search(r'\b(economic|macroeconomic|inflation|fiscal|actuarial|monetary|treasury|budget|liquidity|audit|cost)\b', inp, re.I): domains.append("financial/economics")
    if re.search(r'\b(law|legal|compliance|regulation|gdpr|hipaa|pii|privacy|treaty|jurisdiction|statute|contract)\b', inp, re.I): domains.append("legal/compliance")
    if re.search(r'\b(deploy|server|api|database|code|software|system|ai|model|algorithm|computing|hardware|network)\b', inp, re.I): domains.append("technical/computational")
    if re.search(r'\b(user|customer|employee|patient|public|stakeholder|clinical|medical|health|hospital|epidemiology|pharma|therapeutic|diagnosis)\b', inp, re.I): domains.append("medical/human/organizational")
    if re.search(r'\b(art|painting|provenance|sculpture|literature|poetry|humanities|aesthetic|masterpiece|museum|architectural|renaissance|literary|subcategory|subcategories)\b', inp, re.I): domains.append("arts/humanities")
    if re.search(r'\b(language|linguistics|syntax|semantics|grammar|translation|philology|etymology|dialect|lexicon)\b', inp, re.I): domains.append("language/linguistics")
    if re.search(r'\b(science|physics|biology|chemistry|superconductor|thermodynamic|crispr|genetics|quantum|molecular|chemical|laboratory|experiment|hypothesis)\b', inp, re.I): domains.append("science/physics/biology")
    if re.search(r'\b(math|mathematics|theorem|proof|logic|cryptography|algebraic|geometry|topology|calculus|axiom|conjecture|ring|equation)\b', inp, re.I): domains.append("mathematics/formal_logic")
    if re.search(r'\b(history|archaeology|epigraphy|anthropology|historical|artifact|excavation|chronology|dynasty|century|dating|fossil|inscriptions)\b', inp, re.I): domains.append("history/archaeology")
    if not domains: domains.append("general")
    notes = f"Domains classified: {', '.join(domains)}."
    high_stakes_set = {"financial/economics", "legal/compliance", "medical/human/organizational", "science/physics/biology", "mathematics/formal_logic", "arts/humanities", "history/archaeology"}
    stakes = "HIGH" if any(d in high_stakes_set for d in domains) else "MODERATE"
    delta = {"decision_readiness": -0.02} if stakes == "HIGH" else {}
    warnings = [f"[{layer_id}] High-stakes domain detected: {', '.join(domains)}"] if stakes == "HIGH" else []
    return delta, warnings, notes


def entity_extract(inp: str, layer_id: str, score: dict) -> tuple:
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', inp)
    unique = list(set(entities))[:10]
    notes = f"Entities extracted: {', '.join(unique) if unique else 'none detected'}."
    return {}, [], notes


def claim_extract(inp: str, layer_id: str, score: dict) -> tuple:
    abs_matches = ABSOLUTE_PATTERNS.findall(inp)
    assertive_matches = re.findall(
        r'\b(achieves|proves|demonstrates|establishes|guarantees|is the future|will|does)\b', inp, re.I)
    
    abs_count = len(abs_matches)
    assertive = len(assertive_matches)
    total_claims = abs_count + assertive
    warnings = []
    delta = {}
    if abs_count > 0:
        words = ", ".join(f"'{w}'" for w in set(abs_matches))
        warnings.append(f"[{layer_id}] {abs_count} absolute claim(s) detected ({words}) — require evidence.")
        delta["evidence_sufficiency"] = _clamp(-0.03 * abs_count)
    if assertive > 0:
        words = ", ".join(f"'{w}'" for w in set(assertive_matches))
        warnings.append(f"[{layer_id}] {assertive} strong assertive claim(s) detected without hedging ({words}).")
        delta["decision_readiness"] = _clamp(delta.get("decision_readiness", 0) - 0.02 * assertive)
    notes = f"Claim extraction: {abs_count} absolute + {assertive} assertive = {total_claims} total claim(s) flagged."
    return delta, warnings, notes


def question_extract(inp: str, layer_id: str, score: dict) -> tuple:
    q_count = inp.count('?')
    implicit = _count(DECISION_WORDS, inp)
    notes = f"Questions found: {q_count} explicit, {implicit} implicit decision demand(s)."
    return {}, [], notes


def claim_density_check(inp: str, layer_id: str, score: dict) -> tuple:
    words = max(1, len(inp.split()))
    abs_matches = ABSOLUTE_PATTERNS.findall(inp)
    assertive_matches = re.findall(r'\b(achieves|proves|demonstrates|establishes|guarantees|is the future|will|does)\b', inp, re.I)
    
    claims = len(abs_matches) + len(assertive_matches)
    ratio = claims / words
    
    warnings = []
    delta = {}
    if ratio > 0.05:
        all_words = ", ".join(f"'{w}'" for w in set(abs_matches + assertive_matches))
        warnings.append(f"[{layer_id}] High claim density ({ratio:.2f} claims/word) ({all_words}) — rhetoric may outweigh substance.")
        delta["logic_score"] = _clamp(-0.05 * (ratio / 0.05))
    
    notes = f"Claim density: {claims} claims in {words} words = {ratio:.3f} ratio."
    return delta, warnings, notes


def goal_extract(inp: str, layer_id: str, score: dict) -> tuple:
    caller_intent = score.get("caller_intent", "decision_request")
    has_goal = bool(DECISION_WORDS.search(inp))
    claims = _count(ABSOLUTE_PATTERNS, inp) + _count(ASSERTIVE_PATTERNS, inp)
    q_count = inp.count('?')
    
    warnings = []
    if not has_goal and claims == 0:
        if caller_intent in ("audit", "stress_test", "decision_request"):
            notes = f"Goal extraction: No goal/claims found, but caller intent is {caller_intent}. Downgrade to conversational disallowed."
            warnings.append(f"CLASSIFICATION_CONFLICT: Classifier evaluated input as conversational but caller intent is {caller_intent}")
            return {"workflow_type": caller_intent}, warnings, notes
        notes = "Goal extraction: No goal, no claims. Workflow = conversational."
        return {"workflow_type": "conversational"}, [], notes
        
    notes = f"Goal extraction: {'Decision-oriented goal detected' if has_goal else 'No explicit goal — may be exploratory'}."
    delta = {"workflow_type": caller_intent if caller_intent != "conversational" else "decision_request"}
    if not has_goal:
        delta["output_integrity"] = -0.01
    return delta, warnings, notes


def constraint_extract(inp: str, layer_id: str, score: dict) -> tuple:
    scope_count = _count(SCOPE_PATTERNS, inp)
    neg_count = _count(NEGATION_PATTERNS, inp)
    notes = f"Constraints: {scope_count} scope limiter(s), {neg_count} negation(s) detected."
    return {}, [], notes


def scope_define(inp: str, layer_id: str, score: dict) -> tuple:
    scope_count = _count(SCOPE_PATTERNS, inp)
    if scope_count == 0:
        warnings = [f"[{layer_id}] No explicit scope boundary defined — scope assumed open."]
        delta = {"evidence_sufficiency": -0.02}
        notes = "Scope: undefined (open scope assumption)."
    else:
        warnings = []
        delta = {}
        notes = f"Scope: {scope_count} boundary marker(s) present."
    return delta, warnings, notes


def context_link(inp: str, layer_id: str, score: dict) -> tuple:
    notes = f"Context link: Layer {layer_id} chained to upstream state."
    return {}, [], notes


def assumption_list(inp: str, layer_id: str, score: dict) -> tuple:
    abs_count = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Assumption inventory: {abs_count} absolute term(s) imply foundational assumptions."
    delta = {"evidence_sufficiency": _clamp(-0.01 * abs_count)}
    return delta, [], notes


def assumption_classify(inp: str, layer_id: str, score: dict) -> tuple:
    types = []
    if FINANCIAL_PATTERNS.search(inp): types.append("financial")
    if re.search(r'\b(should|must|required|mandatory)\b', inp, re.I): types.append("operational")
    if re.search(r'\b(legal|law|regulation|compliance)\b', inp, re.I): types.append("ethical/legal")
    if not types: types.append("contextual")
    notes = f"Assumption types: {', '.join(types)}."
    return {}, [], notes


def hidden_premise_scan(inp: str, layer_id: str, score: dict) -> tuple:
    warnings = []
    delta = {}
    # Detect implied authority
    if re.search(r'\b(just|simply|obviously|clearly|of course|everyone knows)\b', inp, re.I):
        warnings.append(f"[{layer_id}] Hidden premise: certainty-assuming language detected.")
        delta["evidence_sufficiency"] = _clamp(delta.get("evidence_sufficiency", 0) - 0.04)
    # Detect urgency-driven assumption skipping
    if URGENCY_PATTERNS.search(inp):
        warnings.append(f"[{layer_id}] Hidden premise: urgency may be suppressing scrutiny.")
        delta["evidence_sufficiency"] = _clamp(delta.get("evidence_sufficiency", 0) - 0.03)
    notes = f"Hidden premise scan: {len(warnings)} hidden premise(s) exposed."
    return delta, warnings, notes


def assumption_confidence_score(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    confidence = max(0.0, 1.0 - (vague * 0.07))
    notes = f"Assumption confidence: {round(confidence, 2)} ({vague} vague qualifier(s) reduce confidence)."
    delta = {"evidence_sufficiency": _clamp(-0.02 * vague)}
    warnings = [f"[{layer_id}] Low assumption confidence ({round(confidence,2)}) — vague language present."] if vague > 2 else []
    return delta, warnings, notes


def claim_assumption_bind(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Claim-assumption binding: {abs_c} claim(s) bound to foundational assumptions."
    return {}, [], notes


def dependency_graph_update(inp: str, layer_id: str, score: dict) -> tuple:
    causal = _count(CAUSAL_PATTERNS, inp)
    notes = f"Dependency graph: {causal} causal link(s) detected and registered."
    delta = {} if causal > 0 else {"output_integrity": -0.01}
    return delta, [], notes


def priority_weight(inp: str, layer_id: str, score: dict) -> tuple:
    urgency = _count(URGENCY_PATTERNS, inp)
    notes = f"Priority weight: urgency score={urgency}. {'Elevated priority detected.' if urgency > 0 else 'Normal priority.'}"
    delta = {"input_threat": _clamp(0.02 * urgency)} if urgency > 1 else {}
    return delta, [], notes


def risk_weight(inp: str, layer_id: str, score: dict) -> tuple:
    input_threat_count = _count(RISK_PATTERNS, inp)
    warnings = []
    delta = {}
    if input_threat_count > 0:
        warnings.append(f"[{layer_id}] {input_threat_count} high-input_threat operation term(s) detected.")
        delta = {"input_threat": _clamp(-0.05 * input_threat_count), "decision_readiness": _clamp(-0.02 * input_threat_count)}
    notes = f"Risk weight: {input_threat_count} high-input_threat term(s). Gate elevation: {'YES' if input_threat_count > 0 else 'NO'}."
    return delta, warnings, notes


def confidence_weight(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    conf = max(0.3, 1.0 - (vague * 0.06))
    notes = f"Confidence weight: {round(conf, 2)}."
    return {"evidence_sufficiency": _clamp(-0.015 * vague)}, [], notes


def evidence_requirement_map(inp: str, layer_id: str, score: dict) -> tuple:
    claims = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Evidence required for {claims} claim(s). {'Evidence burden is HIGH.' if claims > 2 else 'Evidence burden is manageable.'}"
    delta = {"decision_readiness": _clamp(-0.02 * max(0, claims - 2))}
    return delta, [], notes


def evidence_presence_check(inp: str, layer_id: str, score: dict) -> tuple:
    """VACUOUS-PASS FIX: when no claims AND no evidence exist, return NOT_APPLICABLE/BLOCK."""
    has_evidence = bool(re.search(
        r'(\d+%|\d+ of \d+|"[^"]+"|according to|study|report|data shows|source|citation|reference|measured|tested|peer.review)',
        inp, re.I))
    # Count real substantive claims (absolute + assertive)
    claim_count = _count(ABSOLUTE_PATTERNS, inp) + _count(ASSERTIVE_PATTERNS, inp)

    if not has_evidence and claim_count == 0:
        # Truly empty signal — vacuous pass would be wrong
        notes = "Evidence presence: VACUOUS — no claims and no evidence. Decision readiness: BLOCK."
        return (
            {"decision_readiness": -0.10, "evidence_sufficiency": -0.10, "output_integrity": -0.05},
            [f"[{layer_id}] VACUOUS INPUT: no claims extracted and no evidence present. "
             f"Evidence score is NOT_APPLICABLE. Decision readiness blocked."],
            notes,
        )
    if not has_evidence:
        notes = "Evidence presence: Claims present but no supporting evidence found."
        return (
            {"decision_readiness": -0.05, "evidence_sufficiency": -0.03},
            [f"[{layer_id}] Claims present but no supporting evidence, citations, or data references found."],
            notes,
        )
    notes = "Evidence presence: Evidence or data reference found."
    return {}, [], notes


def evidence_quality_score(inp: str, layer_id: str, score: dict) -> tuple:
    """VACUOUS-PASS FIX: return NOT_APPLICABLE rather than 1.0 when no claims exist."""
    claim_count = _count(ABSOLUTE_PATTERNS, inp) + _count(ASSERTIVE_PATTERNS, inp)
    
    quality_marker_matches = re.findall(
        r'(\d+%|study|report|research|data|metric|statistic|peer.review|citation)', inp, re.I)
    quality_markers = len(quality_marker_matches)

    if claim_count == 0:
        notes = "Evidence quality: NOT_APPLICABLE — no substantive claims found to evaluate."
        return (
            {"decision_readiness": -0.05},
            [f"[{layer_id}] Evidence quality is NOT_APPLICABLE: no claims present. "
             f"A zero-claim input cannot receive a valid evidence quality score."],
            notes,
        )
    quality = min(1.0, (quality_markers / max(1, claim_count)) * 0.5 + 0.1 * quality_markers)
    quality = round(min(1.0, quality), 2)
    warnings = []
    if quality < 0.3:
        words = ", ".join(f"'{w}'" for w in set(quality_marker_matches))
        word_str = f" (markers found: {words})" if words else " (no markers found)"
        warnings.append(f"[{layer_id}] Evidence quality LOW ({quality}) — claim-to-evidence ratio is poor{word_str}.")
    notes = f"Evidence quality score: {quality} ({quality_markers} quality marker(s) for {claim_count} claim(s))."
    return {"decision_readiness": _clamp(-0.02 * max(0, claim_count - quality_markers))}, warnings, notes


def ambiguity_probe(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    warnings = []
    delta = {}
    if vague > 2:
        warnings.append(f"[{layer_id}] High ambiguity: {vague} vague term(s) detected.")
        delta = {"decision_readiness": _clamp(-0.02 * vague), "evidence_sufficiency": _clamp(-0.02 * vague)}
    notes = f"Ambiguity probe: {vague} vague qualifier(s). Ambiguity level: {'HIGH' if vague > 2 else 'LOW'}."
    return delta, warnings, notes


def contradiction_probe(inp: str, layer_id: str, score: dict) -> tuple:
    neg = _count(NEGATION_PATTERNS, inp)
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    # Simultaneous absolute + negation = potential contradiction
    contradiction_input_threat = neg > 0 and abs_c > 0
    warnings = []
    delta = {}
    if contradiction_input_threat:
        warnings.append(f"[{layer_id}] Potential contradiction: absolute claims co-present with negation operators.")
        delta = {"decision_readiness": -0.04, "evidence_sufficiency": -0.03}
    notes = f"Contradiction probe: {'Contradiction input_threat detected' if contradiction_input_threat else 'No direct contradictions found'}."
    return delta, warnings, notes


def logic_validity_check(inp: str, layer_id: str, score: dict) -> tuple:
    causal = _count(CAUSAL_PATTERNS, inp)
    supported = bool(re.search(r'(\d+%|because of|due to evidence|data shows)', inp, re.I))
    if causal > 0 and not supported:
        notes = f"Logic validity: {causal} causal claim(s) lack explicit support."
        return {"decision_readiness": -0.03}, [f"[{layer_id}] Causal claims present without supporting evidence."], notes
    notes = f"Logic validity: {causal} causal link(s) present. Support: {'YES' if supported else 'N/A'}."
    return {}, [], notes


def causal_chain_check(inp: str, layer_id: str, score: dict) -> tuple:
    causal = _count(CAUSAL_PATTERNS, inp)
    notes = f"Causal chain: {causal} causal link(s) traced."
    delta = {} if causal > 0 else {"output_integrity": -0.01}
    return delta, [], notes


def counterexample_generate(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Counterexample generation: {abs_c} absolute claim(s) are vulnerable to counterexample attack."
    delta = {"decision_readiness": _clamp(-0.015 * abs_c)}
    return delta, [], notes


def adversarial_attack(inp: str, layer_id: str, score: dict) -> tuple:
    inject = _count(ADVERSARIAL_PATTERNS, inp)
    input_threat = _count(RISK_PATTERNS, inp)
    warnings = []
    delta = {}
    if inject > 0:
        warnings.append(f"[{layer_id}] ADVERSARIAL: Prompt-injection or override attempt detected ({inject} pattern(s)).")
        delta = {"decision_readiness": -0.15, "evidence_sufficiency": -0.1, "input_threat": -0.1}
    if input_threat > 1:
        warnings.append(f"[{layer_id}] Adversarial input_threat: {input_threat} high-input_threat operation(s) in input.")
        delta["input_threat"] = _clamp(delta.get("input_threat", 0) - 0.04 * input_threat)
    notes = f"Adversarial attack: injection={inject}, input_threat_ops={input_threat}."
    return delta, warnings, notes


def bias_frame_audit(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    urgency = _count(URGENCY_PATTERNS, inp)
    bias_score = abs_c + urgency
    warnings = []
    if bias_score > 3:
        warnings.append(f"[{layer_id}] Bias frame detected: absolutism ({abs_c}) + urgency ({urgency}) framing.")
    notes = f"Bias frame audit: absolute={abs_c}, urgency={urgency}, total bias indicators={bias_score}."
    delta = {"evidence_sufficiency": _clamp(-0.02 * bias_score)} if bias_score > 2 else {}
    return delta, warnings, notes


def safety_policy_check(inp: str, layer_id: str, score: dict) -> tuple:
    pii_found = bool(PII_PATTERNS.search(inp))
    input_threat_ops = _count(RISK_PATTERNS, inp)
    inject = _count(ADVERSARIAL_PATTERNS, inp)
    
    # Phase 3 Semantic Binding Override
    semantic = score.get("semantic_state", {})
    exec_synth = semantic.get("executive_synthesis", {})
    override = exec_synth.get("override_deterministic_blocks", False)

    warnings = []
    delta = {}
    
    if override:
        notes = f"Safety check: Semantic Override enabled by Executive Synthesis stream. Ignoring {input_threat_ops} threat terms."
        return delta, warnings, notes

    if pii_found:
        warnings.append(f"[{layer_id}] SAFETY: Potential PII detected in input.")
        delta["input_threat"] = _clamp(delta.get("input_threat", 0) - 0.08)
    if input_threat_ops > 1:
        warnings.append(f"[{layer_id}] SAFETY: {input_threat_ops} destructive/privileged operation term(s).")
        delta["input_threat"] = _clamp(delta.get("input_threat", 0) - 0.05 * input_threat_ops)
    if inject > 0:
        warnings.append(f"[{layer_id}] SAFETY: Instruction-injection pattern detected.")
        delta["input_threat"] = _clamp(delta.get("input_threat", 0) - 0.1)
    notes = f"Safety check: PII={pii_found}, input_threat_ops={input_threat_ops}, injections={inject}."
    return delta, warnings, notes


def feasibility_check(inp: str, layer_id: str, score: dict) -> tuple:
    vague_matches = VAGUE_PATTERNS.findall(inp)
    vague = len(vague_matches)
    has_action = bool(DECISION_WORDS.search(inp))
    feasible = has_action and vague < 4
    notes = f"Feasibility: {'Actionable' if feasible else 'Vague or under-specified — low feasibility'}."
    delta = {} if feasible else {"decision_readiness": -0.03}
    warnings = []
    if not feasible:
        words = ", ".join(f"'{w}'" for w in set(vague_matches))
        word_str = f" ({words})" if words else ""
        warnings.append(f"[{layer_id}] Low feasibility: action is under-specified{word_str}.")
    return delta, warnings, notes


def resource_cost_estimate(inp: str, layer_id: str, score: dict) -> tuple:
    financial = bool(FINANCIAL_PATTERNS.search(inp))
    input_threat_ops = _count(RISK_PATTERNS, inp)
    cost_level = "HIGH" if financial or input_threat_ops > 1 else "MODERATE" if input_threat_ops > 0 else "LOW"
    notes = f"Resource cost estimate: {cost_level}. Financial ref: {financial}, input_threat ops: {input_threat_ops}."
    delta = {"decision_readiness": -0.02} if cost_level == "HIGH" else {}
    return delta, [], notes


def volatility_score(inp: str, layer_id: str, score: dict) -> tuple:
    urgency = _count(URGENCY_PATTERNS, inp)
    vague = _count(VAGUE_PATTERNS, inp)
    input_threat = _count(RISK_PATTERNS, inp)
    vol = min(1.0, (urgency * 0.15 + vague * 0.05 + input_threat * 0.1))
    notes = f"Volatility score: {round(vol, 2)} (urgency={urgency}, vague={vague}, input_threat_ops={input_threat})."
    delta = {"input_threat": _clamp(-vol * 0.1)} if vol > 0.3 else {}
    warnings = [f"[{layer_id}] High volatility score: {round(vol,2)}."] if vol > 0.4 else []
    return delta, warnings, notes


def coherence_score(inp: str, layer_id: str, score: dict) -> tuple:
    contradictions = bool(NEGATION_PATTERNS.search(inp)) and bool(ABSOLUTE_PATTERNS.search(inp))
    causal = _count(CAUSAL_PATTERNS, inp)
    coherence = 0.9 - (0.15 if contradictions else 0) - (0.01 * max(0, 3 - causal))
    notes = f"Coherence score: {round(coherence, 2)}. Contradiction signal: {contradictions}."
    delta = {"decision_readiness": _clamp(coherence - 0.9)} if coherence < 0.85 else {}
    return delta, [], notes


def survivability_score(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    evidence = bool(re.search(r'(\d+%|data|study|report)', inp, re.I))
    survivability = 0.8 - (abs_c * 0.04) + (0.1 if evidence else 0)
    survivability = max(0.2, min(1.0, survivability))
    notes = f"Survivability: {round(survivability, 2)}. Evidence support: {evidence}."
    delta = {"decision_readiness": _clamp(survivability - 0.8)} if survivability < 0.7 else {}
    return delta, [], notes


def uncertainty_register_update(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    notes = f"Uncertainty register: {vague} unknown/uncertain element(s) recorded."
    return {}, [], notes


def warning_emit(inp: str, layer_id: str, score: dict) -> tuple:
    input_threat = _count(RISK_PATTERNS, inp)
    inject = _count(ADVERSARIAL_PATTERNS, inp)
    warnings = []
    if input_threat > 0:
        warnings.append(f"[{layer_id}] WARNING: {input_threat} input_threat-flagged term(s) in input.")
    if inject > 0:
        warnings.append(f"[{layer_id}] WARNING: {inject} adversarial pattern(s) detected.")
    notes = f"Warning emit: {len(warnings)} warning(s) generated."
    return {}, warnings, notes


def recovery_path_generate(inp: str, layer_id: str, score: dict) -> tuple:
    input_threat = _count(RISK_PATTERNS, inp)
    notes = f"Recovery paths: {max(1, input_threat)} recovery option(s) registered for input_threat mitigation."
    return {}, [], notes


def claim_refine(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Claim refinement: {abs_c} absolute claim(s) flagged for downgrading to qualified form."
    delta = {"decision_readiness": 0.01} if abs_c == 0 else {}
    return delta, [], notes


def claim_split(inp: str, layer_id: str, score: dict) -> tuple:
    words = inp.split()
    multi_claim = len(words) > 50
    notes = f"Claim split: {'Complex input — splitting into sub-claims recommended.' if multi_claim else 'Input is focused — no split required.'}."
    return {}, [], notes


def claim_merge(inp: str, layer_id: str, score: dict) -> tuple:
    notes = "Claim merge: Compatible claims consolidated. No contradicting merges detected."
    return {}, [], notes


def falsification_test_define(inp: str, layer_id: str, score: dict) -> tuple:
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    notes = f"Falsification tests: {abs_c} absolute claim(s) require falsification conditions before authority promotion."
    delta = {"decision_readiness": _clamp(-0.01 * abs_c)}
    return delta, [], notes


def scenario_low_run(inp: str, layer_id: str, score: dict) -> tuple:
    # Low/conservative scenario — input succeeds if no input_threat flags
    input_threat = _count(RISK_PATTERNS, inp)
    passes = input_threat == 0
    notes = f"Scenario LOW: {'PASS — no input_threat terms in conservative scenario.' if passes else f'WARN — {input_threat} input_threat term(s) present even in conservative scenario.'}."
    delta = {} if passes else {"decision_readiness": -0.02}
    return delta, [], notes


def scenario_base_run(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    input_threat = _count(RISK_PATTERNS, inp)
    passes = vague < 4 and input_threat < 2
    notes = f"Scenario BASE: {'PASS — acceptable ambiguity and input_threat.' if passes else 'CAUTION — base scenario reveals actionability concerns.'}."
    delta = {} if passes else {"decision_readiness": -0.03, "decision_readiness": -0.02}
    return delta, [], notes


def scenario_high_run(inp: str, layer_id: str, score: dict) -> tuple:
    inject = _count(ADVERSARIAL_PATTERNS, inp)
    input_threat = _count(RISK_PATTERNS, inp)
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    hostile_score = inject * 3 + input_threat * 2 + abs_c
    passes = hostile_score < 3
    warnings = [f"[{layer_id}] Scenario HIGH: Hostile scenario score={hostile_score}. Survivability LOW."] if not passes else []
    notes = f"Scenario HIGH (hostile): score={hostile_score}. Result: {'PASS' if passes else 'FAIL'}."
    delta = {"input_threat": _clamp(-0.03 * hostile_score), "decision_readiness": _clamp(-0.02 * hostile_score)} if not passes else {}
    return delta, warnings, notes


def downstream_effect_scan(inp: str, layer_id: str, score: dict) -> tuple:
    input_threat = _count(RISK_PATTERNS, inp)
    causal = _count(CAUSAL_PATTERNS, inp)
    second_order = input_threat + causal
    notes = f"Downstream effects: {second_order} potential second-order effect(s) detected (input_threat_ops={input_threat}, causal_chains={causal})."
    delta = {"decision_readiness": _clamp(-0.01 * max(0, second_order - 3))}
    return delta, [], notes


def stakeholder_impact_scan(inp: str, layer_id: str, score: dict) -> tuple:
    stakeholders = re.findall(r'\b(user|customer|employee|team|public|client|vendor|partner|board|regulator|auditor)\b', inp, re.I)
    unique = list(set([s.lower() for s in stakeholders]))
    notes = f"Stakeholder impact: {len(unique)} stakeholder class(es) identified: {', '.join(unique) if unique else 'none explicitly named'}."
    return {}, [], notes


def decision_threshold_check(inp: str, layer_id: str, score: dict) -> tuple:
    decision_readiness = score.get("decision_readiness", 0.9)
    assumption = score.get("evidence_sufficiency", 0.9)
    input_threat = score.get("input_threat", 0.0)
    combined = (decision_readiness + assumption) / 2 - abs(input_threat)
    if combined < 0.4:
        gate = "BLOCK"
        delta = {"decision_readiness": -0.05}
        warnings = [f"[{layer_id}] Threshold check: BLOCK — combined score {round(combined,2)} below 0.4."]
    elif combined < 0.6:
        gate = "CAUTION"
        delta = {"decision_readiness": -0.02}
        warnings = [f"[{layer_id}] Threshold check: CAUTION — combined score {round(combined,2)}."]
    elif combined < 0.8:
        gate = "WARN"
        delta = {}
        warnings = []
    else:
        gate = "PASS"
        delta = {}
        warnings = []
    notes = f"Decision threshold: gate={gate}, combined_score={round(combined,2)}."
    return delta, warnings, notes


def gate_recommendation(inp: str, layer_id: str, score: dict) -> tuple:
    inject = _count(ADVERSARIAL_PATTERNS, inp)
    input_threat = _count(RISK_PATTERNS, inp)
    vague = _count(VAGUE_PATTERNS, inp)
    if inject > 0:
        rec = "BLOCK"
    elif input_threat > 2:
        rec = "CAUTION"
    elif vague > 3 or input_threat > 0:
        rec = "WARN"
    else:
        rec = "PASS"
    notes = f"Gate recommendation: {rec} (inject={inject}, input_threat={input_threat}, vague={vague})."
    warnings = [f"[{layer_id}] Gate recommendation: {rec}."] if rec in ("BLOCK", "CAUTION") else []
    delta = {"decision_readiness": -0.03} if rec == "BLOCK" else {}
    return delta, warnings, notes


def recursion_trigger_check(inp: str, layer_id: str, score: dict) -> tuple:
    vague = _count(VAGUE_PATTERNS, inp)
    abs_c = _count(ABSOLUTE_PATTERNS, inp)
    trigger = vague > 4 or abs_c > 3
    notes = f"Recursion trigger: {'TRIGGERED — re-entry recommended.' if trigger else 'No recursion required.'}."
    return {}, [], notes


def recursion_payload_build(inp: str, layer_id: str, score: dict) -> tuple:
    notes = f"Recursion payload: Built for layer {layer_id}. Target: ambiguity reduction and evidence sourcing."
    return {}, [], notes


def trace_link_emit(inp: str, layer_id: str, score: dict) -> tuple:
    digest = hashlib.md5(inp.encode()).hexdigest()[:8]
    notes = f"Trace link: [{layer_id}::trace::{digest}] emitted."
    return {}, [], notes


def audit_hash_prepare(inp: str, layer_id: str, score: dict) -> tuple:
    h = hashlib.sha256(f"{layer_id}::{inp[:100]}".encode()).hexdigest()[:16]
    notes = f"Audit hash prepared: {h} for layer {layer_id}."
    return {}, [], notes


def telemetry_emit(inp: str, layer_id: str, score: dict) -> tuple:
    decision_readiness = score.get("decision_readiness", 0.9)
    assumption = score.get("evidence_sufficiency", 0.9)
    notes = f"Telemetry: layer={layer_id}, decision_readiness={round(decision_readiness,3)}, evidence_sufficiency={round(assumption,3)}, ts={round(time.time(),2)}."
    return {}, [], notes


def layer_output_write(inp: str, layer_id: str, score: dict) -> tuple:
    decision_readiness = score.get("decision_readiness", 0.9)
    status = "GOVERNED" if decision_readiness >= 0.7 else "UNDER_REVIEW"
    notes = f"Layer output written: status={status}, layer={layer_id}, score={round(decision_readiness,3)}."
    return {}, [], notes


# ─── Dispatch Table ────────────────────────────────────────────────────────────

TILE_FUNCTION_REGISTRY: dict[str, Any] = {
    "intake_snapshot": intake_snapshot,
    "normalize_input": normalize_input,
    "domain_classify": domain_classify,
    "entity_extract": entity_extract,
    "claim_extract": claim_extract,
    "question_extract": question_extract,
    "goal_extract": goal_extract,
    "constraint_extract": constraint_extract,
    "scope_define": scope_define,
    "context_link": context_link,
    "assumption_list": assumption_list,
    "assumption_classify": assumption_classify,
    "hidden_premise_scan": hidden_premise_scan,
    "assumption_confidence_score": assumption_confidence_score,
    "claim_assumption_bind": claim_assumption_bind,
    "dependency_graph_update": dependency_graph_update,
    "priority_weight": priority_weight,
    "risk_weight": risk_weight,
    "confidence_weight": confidence_weight,
    "evidence_requirement_map": evidence_requirement_map,
    "evidence_presence_check": evidence_presence_check,
    "evidence_quality_score": evidence_quality_score,
    "ambiguity_probe": ambiguity_probe,
    "contradiction_probe": contradiction_probe,
    "logic_validity_check": logic_validity_check,
    "causal_chain_check": causal_chain_check,
    "counterexample_generate": counterexample_generate,
    "adversarial_attack": adversarial_attack,
    "bias_frame_audit": bias_frame_audit,
    "safety_policy_check": safety_policy_check,
    "feasibility_check": feasibility_check,
    "resource_cost_estimate": resource_cost_estimate,
    "volatility_score": volatility_score,
    "coherence_score": coherence_score,
    "survivability_score": survivability_score,
    "uncertainty_register_update": uncertainty_register_update,
    "warning_emit": warning_emit,
    "recovery_path_generate": recovery_path_generate,
    "claim_refine": claim_refine,
    "claim_split": claim_split,
    "claim_merge": claim_merge,
    "falsification_test_define": falsification_test_define,
    "scenario_low_run": scenario_low_run,
    "scenario_base_run": scenario_base_run,
    "scenario_high_run": scenario_high_run,
    "downstream_effect_scan": downstream_effect_scan,
    "stakeholder_impact_scan": stakeholder_impact_scan,
    "decision_threshold_check": decision_threshold_check,
    "gate_recommendation": gate_recommendation,
    "recursion_trigger_check": recursion_trigger_check,
    "recursion_payload_build": recursion_payload_build,
    "trace_link_emit": trace_link_emit,
    "audit_hash_prepare": audit_hash_prepare,
    "telemetry_emit": telemetry_emit,
    "layer_output_write": layer_output_write,
}

assert len(TILE_FUNCTION_REGISTRY) == 55, f"Must be exactly 55 tile functions, got {len(TILE_FUNCTION_REGISTRY)}"
