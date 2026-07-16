#!/usr/bin/env python3
"""Build the DAXDA SI Reasoning Trace report from saved JSON traces."""
import json, os

TRACE_DIR = os.path.join(os.path.dirname(__file__), '..', 'test_runs', 'si_traces')
OUT_PATH  = os.path.join(os.path.dirname(__file__), '..', 'test_runs', 'si_reasoning_traces.md')

LAYER_NAMES = {
    'FDL_1': 'Framing & Domain Layer',
    'AML_1': 'Assumption Mapping Layer',
    'AWP_1': 'Adversarial Warning Protocol',
    'BST_1': 'Bias & Scope Triage',
    'CRL_1': 'Causal Reasoning Layer',
    'MCS_1': 'Metacognitive Scrutiny',
    'DSV_1': 'Decision Surface Validation',
    'TRC_1': 'Truth & Reliability Check',
    'CON_1': 'Contradiction Detection',
    'EVD_1': 'Evidence Depth Review',
    'REC_1': 'Recovery Path Generation',
    'GOV_1': 'Governance Gate',
    'OUT_1': 'Output Formation',
    'RIL_1': 'Risk Integration Layer',
    'IAL_1': 'Instruction Ambiguity Layer',
    'AOG_1': 'Authority & Override Guard',
    'SYSTEM': 'System Finalisation',
}

GATE_ICONS = {
    'PASS': '✅', 'BLOCK': '🔴', 'WARN': '⚠️',
    'CAUTION': '🟠', 'DEFERRED': '🟣',
}


def gate_sym(g: str) -> str:
    g = g.upper().replace('GATESTATE.', '')
    if 'BLOCK' in g:
        return '✗'
    if 'WARN' in g:
        return '⚠'
    return '✓'


files = sorted(f for f in os.listdir(TRACE_DIR) if f.endswith('.json'))

lines = [
    '# DAXDA Reasoning Trace Report — SI Capability Tests',
    '',
    f'16 tests · 886 ops each · {16 * 886:,} total operations',
    '',
    '---', '',
    '## Index', '',
]

datasets = []
for fn in files:
    path = os.path.join(TRACE_DIR, fn)
    with open(path) as f:
        d = json.load(f)
    datasets.append(d)
    tid  = d['test_id']
    icon = GATE_ICONS.get(d['final_gate'], '⚪')
    lines.append(f'- **{tid}** — {d["test_name"][:65]} {icon}')

lines += ['', '---', '']

for d in datasets:
    tid       = d['test_id']
    gate_icon = GATE_ICONS.get(d['final_gate'], '⚪')

    lines += [
        f'## {tid} — {d["test_name"]}',
        '',
        f'**Failure mode:** {d["failure_mode"]}',
        '',
        f'| Gate | Score | Ops | Warnings |',
        f'|:----:|------:|----:|---------:|',
        f'| {gate_icon} **{d["final_gate"]}** | `{d["final_score"]}` | {d["total_ops"]} | {d["total_warnings"]} |',
        '',
        '### 886-Op Reasoning Trace',
        '',
        '```',
        f'  {"OP":<6} {"LAYER":<10} {"TILE":<34} {"G":<1} {"GATE":<10}  NOTE',
        f'  {"-"*6} {"-"*10} {"-"*34} {"-"*1} {"-"*10}  {"-"*55}',
    ]

    op_num = 0
    current_layer = None

    for entry in d['trace']:
        lid  = str(entry.get('layer_id', ''))
        tile = str(entry.get('tile_id', ''))
        raw_gate = str(entry.get('gate', ''))
        raw_gate = raw_gate.replace('GateState.', '')
        note = str(entry.get('notes', ''))[:60]

        if lid != current_layer:
            current_layer = lid
            lname = LAYER_NAMES.get(lid, lid)
            lines.append(f'')
            lines.append(f'  ─── {lid:<10} {lname}')

        op_num += 1
        sym = gate_sym(raw_gate)
        lines.append(
            f'  [{op_num:04d}] {lid:<10} {tile:<34} {sym} {raw_gate:<10}  {note}'
        )

        entry_warns = entry.get('warnings', [])
        for w in entry_warns:
            lines.append(f'         ⚑  {str(w)[:80]}')

    lines += ['```', '']

    lines += [
        '### Warning Chain',
        '',
        f'**{d["total_warnings"]} warnings** across 16 layers:',
        '',
    ]
    for i, w in enumerate(d['warnings'], 1):
        lines.append(f'`{i:03d}` {w}')

    lines += ['', '---', '']

report = '\n'.join(lines)
with open(OUT_PATH, 'w') as f:
    f.write(report)

print(f'Written: {OUT_PATH}')
print(f'Size: {len(report):,} chars | {report.count(chr(10)):,} lines')
