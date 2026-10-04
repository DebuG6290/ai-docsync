"""Offline scoring of immutable human labels against original archived sections.

Run from repository root: python evals/httpx/measurement-review/score_archived.py
No network, provider client, database writes, or model calls are used.
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from docsync.evaluation.metrics import decision_scores

HERE = Path(__file__).resolve().parent
LABEL_PATH = HERE / 'human-labels.v1.json'
LABEL_COMMIT = '7a1b9a23a1d71c4991c3eddcf3f6ff4ede4017c0'
GROUPS = {
    'controlled change on real HTTPX source': 'A_CONTROLLED_REAL_SOURCE_HTTPX',
    'synthetic': 'B_SYNTHETIC',
    'live fork change on real HTTPX source': 'C_LIVE',
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_text_hash(raw, expected):
    # Git may check out text as LF or CRLF. Accept only that mechanical difference.
    lf = raw.replace(b'\r\n', b'\n')
    if expected not in {sha256(raw), sha256(lf), sha256(lf.replace(b'\n', b'\r\n'))}:
        raise ValueError('Frozen source hash mismatch')


def score():
    frozen_blob = subprocess.check_output([
        'git', 'show', f'{LABEL_COMMIT}:evals/httpx/measurement-review/human-labels.v1.json'
    ], cwd=REPO)
    assert LABEL_PATH.read_bytes().replace(b'\r\n', b'\n') == frozen_blob.replace(b'\r\n', b'\n')
    labels = json.loads(frozen_blob)
    assert labels['status'] == 'FROZEN_HUMAN_CONFIRMED'
    verify_text_hash((HERE / 'human-confirmation.v1.txt').read_bytes(), labels['provenance']['confirmation_sha256'])
    proposed = HERE / 'human-review-proposed.json'
    verify_text_hash(proposed.read_bytes(), labels['provenance']['proposed_packet_sha256'])
    archives = {}
    for path, expected_hash in labels['archived_prediction_sources'].items():
        raw = (REPO / path).read_bytes()
        verify_text_hash(raw, expected_hash)
        archives[path] = json.loads(raw)
    section_rows = []
    case_rows = []
    model_versions = set()
    for case in labels['cases']:
        population = GROUPS[case['population']]
        row = dict(review_id=case['review_id'], case_id=case['case_id'], population=population,
                   before_sha=case['before_sha'], after_sha=case['after_sha'],
                   source=case['source'], expected=case['labels'], predicted={}, scored=False)
        if population == 'C_LIVE':
            row['reason_unscored'] = 'Original per-section model predictions unavailable in inspected read-only archives; human review outcomes and merged documentation are not substituted.'
            case_rows.append(row)
            continue
        archive = archives[case['source']]
        if case['review_id'].startswith('S'):
            candidates = [r for r in archive['scenarios'] if r['scenario'] == int(case['review_id'][1:])]
            location = 'scenarios'
        else:
            candidates = [r for r in archive['cases'] if r['scenario_id'] == case['review_id']]
            location = 'cases'
        assert len(candidates) == 1
        archived = candidates[0]
        assert archived['case_id'] == case['case_id']
        sections = archived['sections'] if location == 'scenarios' else [archived['actual_section']]
        ids = [s['section_id'] for s in sections]
        assert len(ids) == len(set(ids)) and set(ids) == set(case['labels'])
        calls = [c for c in archived['sarvam_calls'] if c.get('operation') == 'impact']
        assert calls and any(c.get('response_contract_validation') == 'passed' for c in calls)
        for call in calls:
            assert (call['model'], call['prompt_version']) == ('sarvam-105b', 'impact.v4')
            model_versions.add((call['model'], call['prompt_version']))
        for section in sections:
            sid = section['section_id']
            prediction = section['decision']
            assert prediction in ('UPDATE', 'NO_CHANGE', 'UNCERTAIN')
            row['predicted'][sid] = prediction
            section_rows.append(dict(population=population, review_id=case['review_id'],
                case_id=case['case_id'], section_id=sid, expected=case['labels'][sid],
                predicted=prediction, correct=prediction == case['labels'][sid],
                source=case['source'], source_collection=location,
                model='sarvam-105b', prompt_version='impact.v4'))
        row.update(scored=True, archive_generated_at=archive['generated_at'],
                   metrics=decision_scores(row['expected'], row['predicted']))
        case_rows.append(row)
    assert model_versions == {('sarvam-105b', 'impact.v4')}
    populations = {}
    for population in [*GROUPS.values(), 'COMBINED_DEVELOPMENT_DIAGNOSTICS_ONLY']:
        cases = [c for c in case_rows if c['population'] == population] if population != 'COMBINED_DEVELOPMENT_DIAGNOSTICS_ONLY' else [c for c in case_rows if c['scored']]
        scored = [c for c in cases if c['scored']]
        # Prefix section IDs with case ID: repeated section IDs across code changes
        # remain distinct labelled judgements, without counting duplicate runs.
        expected = {f"{c['review_id']}|{sid}": value for c in scored for sid, value in c['expected'].items()}
        predicted = {f"{c['review_id']}|{sid}": value for c in scored for sid, value in c['predicted'].items()}
        populations[population] = dict(
            candidate_logical_cases=len(cases), logical_cases_scored=len(scored),
            candidate_section_judgements=sum(len(c['expected']) for c in cases),
            section_judgements_scored=len(expected),
            usable_prediction_cases={'numerator': len(scored), 'denominator': len(cases)},
            metrics=decision_scores(expected, predicted) if scored else None,
            status='scored' if scored else 'UNSCORED_PREDICTIONS_UNAVAILABLE')
    return dict(
        report_version='httpx-impact-archived-human-v1',
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        label_version=labels['label_version'], label_commit=LABEL_COMMIT,
        frozen_label_blob_sha256=sha256(frozen_blob),
        prediction_sources=labels['archived_prediction_sources'],
        metric_implementation_sha256=sha256((REPO / 'docsync/evaluation/metrics.py').read_bytes()),
        model='sarvam-105b', prompt_version='impact.v4',
        new_model_calls=0, populations=populations, cases=case_rows,
        section_predictions=section_rows,
        availability={'confirmed_candidate_cases': 12, 'usable_prediction_cases': 10,
                      'original_review_packet_cases': 13, 'excluded_ambiguous_cases': 1},
        excluded=[*labels['excluded'],
            {'review_ids': ['H5','H8','H10','H11'], 'reason': 'No independent human confirmation in this batch; archived UNCERTAIN fixtures are retained but excluded from this UPDATE/NO_CHANGE task. No claim about uncertainty performance.'},
            {'review_ids': ['S5','S6'], 'reason': 'HITL revision/modification replays, not independent impact cases or original impact predictions.'},
            {'sources': ['evals/httpx/live-report.json','evals/httpx/phase1-live-report.json','evals/phase1_1/original-benchmark.json','evals/phase1_1/report.json'], 'reason': 'Legacy/mismatched impact reasoning contract or incomplete section outputs; no compatibility coercion or selection across repeated runs.'},
            {'source': 'evals/phase1_1/report-v2.json', 'reason': 'Composite duplicates underlying v2 artifacts; not additional cases.'}],
        limitations=[
            'Retrospective DEVELOPMENT labels after historical outputs were observed; not hold-out, current-release or generalized performance.',
            'Synthetic cases are excluded from any CV headline metric; combined aggregate is diagnostics only.',
            'S1, LIVE-5to8 and LIVE-8to9 are one timeout-change family, not three independent capability families.',
            'The scored controlled population is only three logical changes / seven sections; sections within a change are correlated.',
            'Selected binary cases do not assess UNCERTAIN correctness. Excluded fixtures remain visible.',
            'LIVE cases have frozen labels but no recovered original per-section predictions; do not count them as failures or successes.',
        ])


def format_ratio(value):
    if value['value'] is None:
        return f"null ({value['numerator']}/{value['denominator']})"
    return f"{value['numerator']}/{value['denominator']} = {100*value['value']:.2f}%"


def markdown(result):
    lines = ['# Archived impact scoring against human labels v1', '',
        f"Labels frozen in `{LABEL_COMMIT}` before offline scoring. Model: **sarvam-105b**; prompt: **impact.v4**. Archived calls dated 2026-10-02. No new model calls, prompt changes or evaluation reruns.", '',
        'UPDATE is positive. Precision=TP/(TP+FP); recall=TP/(TP+FN); F1=2TP/(2TP+FP+FN); false-negative rate=FN/(TP+FN); accuracy=exact matches/labelled sections; coverage=valid section outputs/labelled sections. Zero denominators are null. Missing/UNCERTAIN positive outputs count as FN; missing/UNCERTAIN negatives are not TN.', '',
        '| Population | Cases scored/candidates | Sections scored/labelled | TP | FP | FN | TN | Precision | Recall | F1 | FNR | Accuracy | Output coverage |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for name, pop in result['populations'].items():
        m = pop['metrics']
        common = f"| {name} | {pop['logical_cases_scored']}/{pop['candidate_logical_cases']} | {pop['section_judgements_scored']}/{pop['candidate_section_judgements']} |"
        if m is None:
            lines.append(common + ' unscored | unscored | unscored | unscored | N/A | N/A | N/A | N/A | N/A | N/A |')
        else:
            counts = m['counts']
            values = [str(counts[k]) for k in ('tp','fp','fn','tn')]
            values += [format_ratio(m[k]) for k in ('precision','recall','f1','false_negative_rate','accuracy','output_coverage')]
            lines.append(common + ' ' + ' | '.join(values) + ' |')
    lines += ['', '## Every scored section', '',
              '| Case | Section | Human label | Original model prediction |', '|---|---|---|---|']
    for row in result['section_predictions']:
        lines.append(f"| {row['review_id']} | {row['section_id']} | {row['expected']} | {row['predicted']} |")
    lines += ['', '## Availability and exclusions', '',
        '- Controlled: 3/3 usable archived prediction cases; synthetic: 7/7; live: 0/2. Total: 10/12 confirmed candidate cases, or 10/13 in the original packet including excluded S3.',
        '- S3: excluded as ambiguous / not adjudicated by the human. Adding an adjacent public property does not itself make the existing section materially incorrect, misleading or insufficient.',
        '- LIVE-5to8 and LIVE-8to9: labels frozen (six sections); original predictions unavailable in inspected read-only sources. They are unscored, not operational FN. No human review or merged-doc substitutions.',
        '- H5/H8/H10/H11: no independent human confirmation in this batch; uncertainty fixtures remain inventoried, not silently counted as passing or evaluated here.',
        '- S5/S6: HITL replays, not independent code-change cases. Earlier contracts are excluded rather than coerced. report-v2.json is a composite duplicate.', '',
        '## Limits on claims', '']
    lines += ['- ' + limit for limit in result['limitations']]
    lines += ['', 'The population-specific confusion matrices, source hashes and exact case provenance are in scoring.v1.json. Section-level results are in scoring.v1.csv. The original proposed review packet and archived outputs remain unchanged.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    # Published reports are append-only: a future score requires a new version.
    outputs = [HERE / n for n in ('scoring.v1.json','scoring.v1.csv','SCORING.v1.md')]
    if any(p.exists() for p in outputs):
        raise SystemExit('Version v1 already exists; refusing to overwrite historical results.')
    result = score()
    outputs[0].write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    with outputs[1].open('x', encoding='utf-8', newline='') as stream:
        rows = result['section_predictions']
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    outputs[2].write_text(markdown(result), encoding='utf-8')
    print(markdown(result))
