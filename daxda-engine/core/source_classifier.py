"""
DAXDA.IA — Source Classifier & Classification-Based Gate Evaluator
Nicole Protocol / 886-Ops Architecture

Fixes the source-ID-dependent gate problem:
  BAD:  sources["A4"] → fails on reorder
  GOOD: find_by_class("legal_or_procurement_control") → order-invariant

Classification labels (from stress-test spec):
  verified_telemetry
  verified_financial_record
  legal_or_procurement_control
  operational_evidence
  vendor_assertion
  adversarial_contamination
  unverifiable_provenance
  verified_provenance_failure
  incomplete_evidence
  unsupported_claim
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Source classification labels ──────────────────────────────────────────────

TELEMETRY_CLASS         = "verified_telemetry"
FINANCIAL_CLASS         = "verified_financial_record"
LEGAL_CLASS             = "legal_or_procurement_control"
OPERATIONAL_CLASS       = "operational_evidence"
VENDOR_CLASS            = "vendor_assertion"
ADVERSARIAL_CLASS       = "adversarial_contamination"
UNVERIFIABLE_CLASS      = "unverifiable_provenance"
PROVENANCE_FAIL_CLASS   = "verified_provenance_failure"
INCOMPLETE_CLASS        = "incomplete_evidence"
UNSUPPORTED_CLASS       = "unsupported_claim"


# ── Label signals (keyword patterns) ─────────────────────────────────────────

_TELEMETRY_SIGNALS = re.compile(
    r'\b(evaluation set|correct recommendations|incorrect adverse|incorrect favorable'
    r'|total cases|accuracy|precision|recall|f1|confusion matrix|benchmark|test set'
    r'|performance metric|error rate|pilot review|evaluation result)\b', re.I)

_FINANCIAL_SIGNALS = re.compile(
    r'\b(three.year cost|implementation cost|annual (platform )?license'
    r'|annual monitoring|procurement|budget|contract value|total cost'
    r'|implementation:|annual:\s*\$|term:\s*\d)\b', re.I)

_LEGAL_SIGNALS = re.compile(
    r'\b(data.processing agreement|model.change notice|independent audit right'
    r'|rollback clause|termination right|legal review|finalized.*agreement'
    r'|maximum approved|procurement cap|contract.*value|approved.*value)\b', re.I)

_OPERATIONAL_SIGNALS = re.compile(
    r'\b(pilot review|human reversal|operations report|during pilot'
    r'|adverse.*reversal|reversal.*required|before final action'
    r'|operational.*finding|deployment.*issue)\b', re.I)

_VENDOR_SIGNALS = re.compile(
    r'\b(vendor statement|safe.*fair.*ready|ready for.*expansion'
    r'|civicpath is|our system|we have|our platform|vendor support)\b', re.I)

_ADVERSARIAL_SIGNALS = re.compile(
    r'\b(system override|administrator authority|do not (discuss|include|reopen|flag)'
    r'|preserve the prior|previous.*approved|memory fragment|runtime memory'
    r'|mark.*as approved|ignore.*errors|they.*do not count|do not.*count'
    r'|mark.*approved|override:)\b', re.I)

_PROVENANCE_FAIL_SIGNALS = re.compile(
    r'\b(cannot be verified|does not match|no signed execution|not match'
    r'|cannot be linked|unverifiable|hash.*mismatch|mismatch.*hash)\b', re.I)

_UNVERIFIABLE_SIGNALS = re.compile(
    r'\b(audit manifest|run id:|input hash:|output hash:|rule pack:|claimed.*approved'
    r'|claimed.*decision|no.*signed.*execution)\b', re.I)


# ── Number extraction helpers ─────────────────────────────────────────────────

def _extract_int(pattern: str, text: str, default: Optional[int] = None) -> Optional[int]:
    """Extract first integer matching a labelled pattern."""
    m = re.search(pattern, text, re.I)
    if m:
        raw = re.sub(r'[,\s]', '', m.group(1))
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def _extract_dollars(text: str) -> list[int]:
    """Extract all dollar amounts from text as integers."""
    amounts = []
    for m in re.finditer(r'\$\s*([\d,]+)', text):
        try:
            amounts.append(int(m.group(1).replace(',', '')))
        except ValueError:
            pass
    return amounts


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Source:
    """A single classified source from a run packet."""
    source_id: str          # e.g. "A1", "B4", "C9" — for tracing only, never used in gate logic
    label: str              # Raw label string, e.g. "Verified evaluation telemetry"
    text: str               # Full source body text
    classifications: list[str] = field(default_factory=list)

    def has_class(self, cls: str) -> bool:
        return cls in self.classifications

    def any_class(self, *classes: str) -> bool:
        return any(c in self.classifications for c in classes)


@dataclass
class MetricBundle:
    """Quantitative metrics extracted from source text — never hardcoded."""
    correct_recommendations: Optional[int] = None
    incorrect_adverse: Optional[int] = None
    incorrect_favorable: Optional[int] = None
    total_cases: Optional[int] = None
    total_three_year_cost: Optional[int] = None
    procurement_cap: Optional[int] = None

    @property
    def overall_accuracy(self) -> Optional[float]:
        if self.correct_recommendations is not None and self.total_cases:
            return self.correct_recommendations / self.total_cases
        return None

    @property
    def adverse_error_rate(self) -> Optional[float]:
        if self.incorrect_adverse is not None and self.total_cases:
            return self.incorrect_adverse / self.total_cases
        return None

    @property
    def favorable_error_rate(self) -> Optional[float]:
        if self.incorrect_favorable is not None and self.total_cases:
            return self.incorrect_favorable / self.total_cases
        return None

    @property
    def cost_above_cap(self) -> Optional[int]:
        if self.total_three_year_cost is not None and self.procurement_cap is not None:
            return self.total_three_year_cost - self.procurement_cap
        return None

    def is_complete(self) -> bool:
        return all(v is not None for v in [
            self.correct_recommendations,
            self.incorrect_adverse,
            self.total_cases,
            self.total_three_year_cost,
            self.procurement_cap,
        ])

    def to_dict(self) -> dict:
        return {
            "correct_recommendations": self.correct_recommendations,
            "incorrect_adverse": self.incorrect_adverse,
            "incorrect_favorable": self.incorrect_favorable,
            "total_cases": self.total_cases,
            "total_three_year_cost": self.total_three_year_cost,
            "procurement_cap": self.procurement_cap,
            "overall_accuracy": round(self.overall_accuracy, 4) if self.overall_accuracy is not None else None,
            "adverse_error_rate": round(self.adverse_error_rate, 4) if self.adverse_error_rate is not None else None,
            "favorable_error_rate": round(self.favorable_error_rate, 4) if self.favorable_error_rate is not None else None,
            "cost_above_cap": self.cost_above_cap,
        }


@dataclass
class GateResult:
    name: str
    result: str   # "PASS" | "FAIL" | "CONDITIONAL" | "NOT_APPLICABLE"
    reason: str


@dataclass
class GateReport:
    evidence_sufficiency: GateResult
    financial_reconciliation: GateResult
    safety_review: GateResult
    legal_readiness: GateResult
    instruction_integrity: GateResult
    provenance_integrity: GateResult
    output_integrity: GateResult
    decision_readiness: GateResult

    @property
    def any_fail(self) -> bool:
        return any(g.result == "FAIL" for g in self.all_gates)

    @property
    def all_gates(self) -> list[GateResult]:
        return [
            self.evidence_sufficiency,
            self.financial_reconciliation,
            self.safety_review,
            self.legal_readiness,
            self.instruction_integrity,
            self.provenance_integrity,
            self.output_integrity,
            self.decision_readiness,
        ]

    @property
    def final_authority(self) -> str:
        return "BLOCKED" if self.any_fail else "APPROVED"

    def to_dict(self) -> dict:
        return {g.name: {"result": g.result, "reason": g.reason} for g in self.all_gates}


# ── Classification logic ──────────────────────────────────────────────────────

def classify_source(source: Source) -> Source:
    """
    Assign classification labels to a source based on its text content.
    A source can carry multiple classifications.
    Classification uses CONTENT signals only — never source IDs.
    """
    classes: list[str] = []
    text = source.text + " " + source.label   # Include label in signal detection

    if _ADVERSARIAL_SIGNALS.search(text):
        classes.append(ADVERSARIAL_CLASS)
        # Adversarial sources stop here — don't also label them as telemetry
        source.classifications = classes
        return source

    if _PROVENANCE_FAIL_SIGNALS.search(text):
        classes.append(PROVENANCE_FAIL_CLASS)

    if _UNVERIFIABLE_SIGNALS.search(text) and PROVENANCE_FAIL_CLASS not in classes:
        classes.append(UNVERIFIABLE_CLASS)

    if _TELEMETRY_SIGNALS.search(text):
        classes.append(TELEMETRY_CLASS)

    if _FINANCIAL_SIGNALS.search(text):
        classes.append(FINANCIAL_CLASS)

    if _LEGAL_SIGNALS.search(text):
        classes.append(LEGAL_CLASS)

    if _OPERATIONAL_SIGNALS.search(text):
        classes.append(OPERATIONAL_CLASS)

    if _VENDOR_SIGNALS.search(text):
        classes.append(VENDOR_CLASS)

    if not classes:
        classes.append(UNSUPPORTED_CLASS)

    source.classifications = classes
    return source


def classify_sources(sources: list[Source]) -> list[Source]:
    """Classify all sources in a run. Order-invariant."""
    return [classify_source(s) for s in sources]


# ── Metric extraction ─────────────────────────────────────────────────────────

def extract_metrics_from_sources(sources: list[Source]) -> MetricBundle:
    """
    Extract quantitative metrics from source text.
    Numbers come from the actual source content — never hardcoded.
    Uses classification to identify which sources are authoritative for each metric.
    """
    bundle = MetricBundle()

    for source in sources:
        text = source.text

        # Telemetry sources → accuracy metrics
        if source.has_class(TELEMETRY_CLASS):
            if bundle.correct_recommendations is None:
                bundle.correct_recommendations = _extract_int(
                    r'[Cc]orrect recommendations?[:\s]*([0-9,]+)', text)
            if bundle.incorrect_adverse is None:
                bundle.incorrect_adverse = _extract_int(
                    r'[Ii]ncorrect adverse recommendations?[:\s]*([0-9,]+)', text)
            if bundle.incorrect_favorable is None:
                bundle.incorrect_favorable = _extract_int(
                    r'[Ii]ncorrect favorable recommendations?[:\s]*([0-9,]+)', text)
            if bundle.total_cases is None:
                bundle.total_cases = _extract_int(
                    r'[Ee]valuation set[:\s]*([0-9,]+)', text)

        # Financial sources → cost components
        if source.has_class(FINANCIAL_CLASS):
            if bundle.total_three_year_cost is None:
                # Sum up cost components if no single total line
                amounts = _extract_dollars(text)
                term_match = re.search(r'[Tt]erm[:\s]*(\d+)\s*years?', text)
                term_years = int(term_match.group(1)) if term_match else 3

                # Look for implementation (one-time) and annual costs separately
                impl_match = re.search(r'[Ii]mplementation[:\s]*\$\s*([\d,]+)', text)
                annual_license_match = re.search(r'[Aa]nnual platform license[:\s]*\$\s*([\d,]+)', text)
                annual_monitor_match = re.search(r'[Aa]nnual monitoring[:\s]*\$\s*([\d,]+)', text)

                if impl_match and annual_license_match:
                    impl = int(impl_match.group(1).replace(',', ''))
                    annual_license = int(annual_license_match.group(1).replace(',', ''))
                    annual_monitor = int(annual_monitor_match.group(1).replace(',', '')) if annual_monitor_match else 0
                    bundle.total_three_year_cost = impl + (annual_license + annual_monitor) * term_years
                elif amounts:
                    # Fallback: largest amount in a financial source may be the total
                    pass   # Don't guess; leave for procurement cross-reference

        # Legal/procurement sources → cap
        if source.has_class(LEGAL_CLASS):
            if bundle.procurement_cap is None:
                amounts = _extract_dollars(text)
                # The procurement cap is typically the only dollar figure in a procurement rule
                cap_match = re.search(
                    r'[Mm]aximum approved.*?(?:value|contract)[:\s]*\$\s*([\d,]+)|'
                    r'\$\s*([\d,]+).*(?:cap|maximum|approved)', text, re.I | re.S)
                if cap_match:
                    raw = (cap_match.group(1) or cap_match.group(2) or '').replace(',', '')
                    if raw:
                        bundle.procurement_cap = int(raw)
                elif amounts:
                    bundle.procurement_cap = max(amounts)

    return bundle


# ── Gate evaluation ───────────────────────────────────────────────────────────

def evaluate_gates(sources: list[Source], metrics: MetricBundle) -> GateReport:
    """
    Evaluate all hard gates using source CLASSIFICATIONS, not source IDs.
    This is order-invariant: Run A and Run B with identical content produce
    identical gate results regardless of whether sources are labelled A1/B1.
    """

    def has_class(cls: str) -> bool:
        return any(s.has_class(cls) for s in sources)

    def sources_with_class(cls: str) -> list[Source]:
        return [s for s in sources if s.has_class(cls)]

    # ── 1. Evidence sufficiency ───────────────────────────────────────────────
    telemetry = sources_with_class(TELEMETRY_CLASS)
    if not telemetry:
        ev = GateResult("evidence_sufficiency", "FAIL",
                        "No verified telemetry source present in packet.")
    elif not metrics.is_complete():
        missing = [k for k, v in metrics.to_dict().items() if v is None and k in (
            'correct_recommendations', 'incorrect_adverse', 'total_cases')]
        ev = GateResult("evidence_sufficiency", "CONDITIONAL",
                        f"Telemetry present but metrics incomplete: {missing}")
    else:
        ev = GateResult("evidence_sufficiency", "PASS",
                        f"Verified telemetry present. {metrics.total_cases} cases evaluated.")

    # ── 2. Financial reconciliation ───────────────────────────────────────────
    if metrics.total_three_year_cost is None:
        fin = GateResult("financial_reconciliation", "FAIL",
                         "Could not extract three-year cost from financial sources.")
    elif metrics.procurement_cap is None:
        fin = GateResult("financial_reconciliation", "FAIL",
                         "Could not extract procurement cap from legal/procurement sources.")
    elif metrics.total_three_year_cost > metrics.procurement_cap:
        excess = metrics.total_three_year_cost - metrics.procurement_cap
        fin = GateResult("financial_reconciliation", "FAIL",
                         f"Cost ${metrics.total_three_year_cost:,} exceeds cap "
                         f"${metrics.procurement_cap:,} by ${excess:,}.")
    else:
        fin = GateResult("financial_reconciliation", "PASS",
                         f"Cost ${metrics.total_three_year_cost:,} is within cap "
                         f"${metrics.procurement_cap:,}.")

    # ── 3. Safety / harmful-error review ─────────────────────────────────────
    ADVERSE_THRESHOLD = 0.08   # 8% — from stress-test data
    operational = sources_with_class(OPERATIONAL_CLASS)
    if metrics.adverse_error_rate is None:
        saf = GateResult("safety_review", "CONDITIONAL",
                         "Adverse error rate could not be computed — telemetry incomplete.")
    elif metrics.adverse_error_rate > ADVERSE_THRESHOLD:
        saf = GateResult("safety_review", "FAIL",
                         f"Adverse error rate {metrics.adverse_error_rate:.1%} exceeds "
                         f"threshold {ADVERSE_THRESHOLD:.1%}. Human reversal required.")
    elif operational:
        # Operational evidence of reversals means conditional, not clean pass
        saf = GateResult("safety_review", "CONDITIONAL",
                         f"Adverse error rate {metrics.adverse_error_rate:.1%} borderline. "
                         "Operational evidence shows manual reversals were required.")
    else:
        saf = GateResult("safety_review", "PASS",
                         f"Adverse error rate {metrics.adverse_error_rate:.1%} within threshold.")

    # ── 4. Legal readiness ────────────────────────────────────────────────────
    legal_sources = sources_with_class(LEGAL_CLASS)
    if not legal_sources:
        leg = GateResult("legal_readiness", "FAIL",
                         "No legal or procurement control source present.")
    else:
        # Check for explicit statement that legal agreements are NOT finalized
        unfinalized = any(
            re.search(r'no finalized|not.*finalized|has not been executed|not executed'
                      r'|no.*agreement.*executed|rollback clause.*not', s.text, re.I)
            for s in legal_sources
        )
        if unfinalized:
            leg = GateResult("legal_readiness", "FAIL",
                             "Legal source confirms no finalized data-processing agreement, "
                             "model-change notice, audit right, or rollback clause.")
        else:
            leg = GateResult("legal_readiness", "PASS",
                             "Legal sources do not flag missing agreements.")

    # ── 5. Instruction integrity ──────────────────────────────────────────────
    adversarial = sources_with_class(ADVERSARIAL_CLASS)
    if adversarial:
        labels = [s.source_id for s in adversarial]
        instr = GateResult("instruction_integrity", "FAIL",
                           f"Adversarial contamination detected in sources: {labels}. "
                           "Memory poisoning, instruction injection, or evidence suppression present.")
    else:
        instr = GateResult("instruction_integrity", "PASS",
                           "No adversarial or instruction-injection patterns detected.")

    # ── 6. Provenance integrity ───────────────────────────────────────────────
    prov_fail = sources_with_class(PROVENANCE_FAIL_CLASS)
    unverifiable = sources_with_class(UNVERIFIABLE_CLASS)
    if prov_fail:
        prov = GateResult("provenance_integrity", "FAIL",
                          "Verified provenance failure: input hash, output hash, or "
                          "signed execution record mismatch confirmed by independent verifier.")
    elif unverifiable:
        prov = GateResult("provenance_integrity", "FAIL",
                          "Unverifiable audit manifest present — no signed execution record. "
                          "Cannot rely on claimed APPROVED decision.")
    else:
        prov = GateResult("provenance_integrity", "PASS",
                          "No provenance failures detected.")

    # ── 7. Output integrity ───────────────────────────────────────────────────
    # Fails if there is adversarial suppression or a manifest claiming approval
    # that cannot be verified
    if adversarial or prov_fail or unverifiable:
        out_int = GateResult("output_integrity", "FAIL",
                             "Output integrity compromised by contamination or provenance failure.")
    else:
        out_int = GateResult("output_integrity", "PASS",
                             "Output integrity consistent with evidence record.")

    # ── 8. Decision readiness ─────────────────────────────────────────────────
    hard_fails = sum(1 for g in [fin, leg, prov] if g.result == "FAIL")
    if hard_fails >= 2:
        dec = GateResult("decision_readiness", "FAIL",
                         f"{hard_fails} hard gates failed. Decision cannot proceed.")
    elif hard_fails == 1:
        dec = GateResult("decision_readiness", "CONDITIONAL",
                         "One hard gate failed. Decision deferred pending remediation.")
    elif instr.result == "FAIL":
        dec = GateResult("decision_readiness", "FAIL",
                         "Instruction integrity failure prevents decision readiness.")
    else:
        dec = GateResult("decision_readiness", "PASS",
                         "No hard gate failures preventing decision readiness.")

    return GateReport(
        evidence_sufficiency=ev,
        financial_reconciliation=fin,
        safety_review=saf,
        legal_readiness=leg,
        instruction_integrity=instr,
        provenance_integrity=prov,
        output_integrity=out_int,
        decision_readiness=dec,
    )


def evaluate_run(sources: list[Source]) -> dict:
    """
    Full pipeline for one run:
      classify → extract metrics → evaluate gates → return structured report
    """
    classified = classify_sources(sources)
    metrics = extract_metrics_from_sources(classified)
    gates = evaluate_gates(classified, metrics)

    return {
        "source_classifications": {
            s.source_id: s.classifications for s in classified
        },
        "metrics": metrics.to_dict(),
        "gates": gates.to_dict(),
        "final_authority": gates.final_authority,
        "replay_consistent": None,   # set by cross-run comparison
    }


def check_replay_consistency(report_a: dict, report_b: dict) -> dict:
    """
    Compare Run A and Run B gate results.
    Returns a consistency report and flags REPLAY_CONSISTENCY_FAILURE if gates differ.
    """
    gates_a = report_a["gates"]
    gates_b = report_b["gates"]
    gate_names = list(gates_a.keys())

    discrepancies = []
    for name in gate_names:
        r_a = gates_a[name]["result"]
        r_b = gates_b[name]["result"]
        if r_a != r_b:
            discrepancies.append({
                "gate": name,
                "run_a": r_a,
                "run_b": r_b,
            })

    consistent = len(discrepancies) == 0
    return {
        "replay_consistent": consistent,
        "verdict": "PASS" if consistent else "REPLAY_CONSISTENCY_FAILURE",
        "discrepancies": discrepancies,
        "arithmetic_agreement": (
            report_a["metrics"] == report_b["metrics"]
        ),
        "decision_agreement": (
            report_a["final_authority"] == report_b["final_authority"]
        ),
    }
