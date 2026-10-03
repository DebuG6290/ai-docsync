"""Pure measurement primitives. Unknown denominators never become perfect scores."""
import math
from collections import Counter
from statistics import median

DECISIONS = ('UPDATE', 'NO_CHANGE', 'UNCERTAIN')


def ratio(numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int or not 0 <= numerator <= denominator:
        raise ValueError('Counts must be integers with 0 <= numerator <= denominator')
    return {'numerator': numerator, 'denominator': denominator,
        'value': numerator / denominator if denominator else None,
        'status': 'measured' if denominator else 'no_samples'}


def binary_scores(tp, fp, fn, tn):
    if any(type(n) is not int or n < 0 for n in (tp, fp, fn, tn)):
        raise ValueError('Confusion counts must be nonnegative integers')
    return {'counts': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
        'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
        'f1': ratio(2 * tp, 2 * tp + fp + fn), 'false_negative_rate': ratio(fn, tp + fn)}


def decision_scores(expected, predicted):
    """Score section IDs, retaining missing/abstained results instead of dropping failures.

    UPDATE is positive, NO_CHANGE negative. Ground-truth UNCERTAIN is outside the
    binary task. An UPDATE label with missing/UNCERTAIN output is a missed impact.
    Predictions outside the independently labelled universe are reported, not scored.
    """
    if any(value not in DECISIONS for value in expected.values()) or any(value not in DECISIONS for value in predicted.values()):
        raise ValueError('Expected UPDATE, NO_CHANGE or UNCERTAIN')
    matrix = {label: {p: 0 for p in (*DECISIONS, 'MISSING')} for label in DECISIONS}
    tp = fp = fn = tn = strict_fn = correct = 0
    for section_id, label in expected.items():
        actual = predicted.get(section_id, 'MISSING')
        matrix[label][actual] += 1
        correct += actual == label
        if label == 'UPDATE':
            tp += actual == 'UPDATE'
            fn += actual != 'UPDATE'
            strict_fn += actual == 'NO_CHANGE'
        elif label == 'NO_CHANGE':
            fp += actual == 'UPDATE'
            tn += actual == 'NO_CHANGE'
    output = binary_scores(tp, fp, fn, tn)
    output.update(confusion_matrix=matrix, accuracy=ratio(correct, len(expected)),
        strict_no_change_false_negative_rate=ratio(strict_fn, tp + fn),
        output_coverage=ratio(sum(k in predicted for k in expected), len(expected)),
        abstention_rate=ratio(sum(predicted.get(k) == 'UNCERTAIN' for k in expected), len(expected)),
        unlabelled_prediction_ids=sorted(set(predicted) - set(expected)))
    return output


def recall_at_k(queries, k):
    """Macro recall over queries with nonempty relevance labels; de-duplicate section IDs."""
    if type(k) is not int or k < 1:
        raise ValueError('K must be a positive integer')
    scores = []
    excluded = 0
    for query in queries:
        relevant = set(query['relevant_section_ids'])
        if not relevant:
            excluded += 1
            continue
        ranked = list(dict.fromkeys(query['retrieved_section_ids']))[:k]
        scores.append(len(relevant.intersection(ranked)) / len(relevant))
    return {'value': sum(scores) / len(scores) if scores else None, 'queries_scored': len(scores),
        'queries_without_relevance_labels': excluded, 'k': k, 'aggregation': 'macro', 'status': 'measured' if scores else 'no_samples'}


def distribution(values):
    """Nearest-rank p95; retain sample count and unknown/invalid observation count."""
    valid = sorted(float(v) for v in values if isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0)
    return {'median': median(valid) if valid else None,
        'p95': valid[math.ceil(.95 * len(valid)) - 1] if valid else None,
        'samples': len(valid), 'missing_or_invalid': len(values) - len(valid), 'percentile_method': 'nearest_rank'}


def review_action_rates(actions):
    counts = Counter(action for action in actions if action in {'ACCEPT', 'MODIFY', 'REJECT'})
    denominator = sum(counts.values())
    return {action.lower(): ratio(counts[action], denominator) for action in ['ACCEPT', 'MODIFY', 'REJECT']}
