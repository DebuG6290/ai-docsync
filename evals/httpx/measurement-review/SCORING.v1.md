# Archived impact scoring against human labels v1

Labels frozen in `7a1b9a23a1d71c4991c3eddcf3f6ff4ede4017c0` before offline scoring. Model: **sarvam-105b**; prompt: **impact.v4**. Archived calls dated 2026-10-02. No new model calls, prompt changes or evaluation reruns.

UPDATE is positive. Precision=TP/(TP+FP); recall=TP/(TP+FN); F1=2TP/(2TP+FP+FN); false-negative rate=FN/(TP+FN); accuracy=exact matches/labelled sections; coverage=valid section outputs/labelled sections. Zero denominators are null. Missing/UNCERTAIN positive outputs count as FN; missing/UNCERTAIN negatives are not TN.

| Population | Cases scored/candidates | Sections scored/labelled | TP | FP | FN | TN | Precision | Recall | F1 | FNR | Accuracy | Output coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_CONTROLLED_REAL_SOURCE_HTTPX | 3/3 | 7/7 | 6 | 0 | 0 | 1 | 6/6 = 100.00% | 6/6 = 100.00% | 12/12 = 100.00% | 0/6 = 0.00% | 7/7 = 100.00% | 7/7 = 100.00% |
| B_SYNTHETIC | 7/7 | 7/7 | 5 | 0 | 0 | 2 | 5/5 = 100.00% | 5/5 = 100.00% | 10/10 = 100.00% | 0/5 = 0.00% | 7/7 = 100.00% | 7/7 = 100.00% |
| C_LIVE | 0/2 | 0/6 | unscored | unscored | unscored | unscored | N/A | N/A | N/A | N/A | N/A | N/A |
| COMBINED_DEVELOPMENT_DIAGNOSTICS_ONLY | 10/10 | 14/14 | 11 | 0 | 0 | 3 | 11/11 = 100.00% | 11/11 = 100.00% | 22/22 = 100.00% | 0/11 = 0.00% | 14/14 = 100.00% | 14/14 = 100.00% |

## Every scored section

| Case | Section | Human label | Original model prediction |
|---|---|---|---|
| S1 | docs/advanced/timeouts.md::__intro__ | UPDATE | UPDATE |
| S1 | docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client | UPDATE | UPDATE |
| S1 | docs/quickstart.md::timeouts | UPDATE | UPDATE |
| S2 | docs/advanced/timeouts.md::fine-tuning-the-configuration | NO_CHANGE | NO_CHANGE |
| S4 | docs/advanced/timeouts.md::__intro__ | UPDATE | UPDATE |
| S4 | docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client | UPDATE | UPDATE |
| S4 | docs/quickstart.md::timeouts | UPDATE | UPDATE |
| H1 | docs/behavior.md::display-title | UPDATE | UPDATE |
| H2 | docs/behavior.md::protocol-version | UPDATE | UPDATE |
| H3 | docs/behavior.md::normalize-name | NO_CHANGE | NO_CHANGE |
| H4 | docs/behavior.md::maximum-attempts | NO_CHANGE | NO_CHANGE |
| H6 | docs/behavior.md::worker-count | UPDATE | UPDATE |
| H7 | docs/behavior.md::retry-classification | UPDATE | UPDATE |
| H9 | docs/behavior.md::retention-days | UPDATE | UPDATE |

## Availability and exclusions

- Controlled: 3/3 usable archived prediction cases; synthetic: 7/7; live: 0/2. Total: 10/12 confirmed candidate cases, or 10/13 in the original packet including excluded S3.
- S3: excluded as ambiguous / not adjudicated by the human. Adding an adjacent public property does not itself make the existing section materially incorrect, misleading or insufficient.
- LIVE-5to8 and LIVE-8to9: labels frozen (six sections); original predictions unavailable in inspected read-only sources. They are unscored, not operational FN. No human review or merged-doc substitutions.
- H5/H8/H10/H11: no independent human confirmation in this batch; uncertainty fixtures remain inventoried, not silently counted as passing or evaluated here.
- S5/S6: HITL replays, not independent code-change cases. Earlier contracts are excluded rather than coerced. report-v2.json is a composite duplicate.

## Limits on claims

- Retrospective DEVELOPMENT labels after historical outputs were observed; not hold-out, current-release or generalized performance.
- Synthetic cases are excluded from any CV headline metric; combined aggregate is diagnostics only.
- S1, LIVE-5to8 and LIVE-8to9 are one timeout-change family, not three independent capability families.
- The scored controlled population is only three logical changes / seven sections; sections within a change are correlated.
- Selected binary cases do not assess UNCERTAIN correctness. Excluded fixtures remain visible.
- LIVE cases have frozen labels but no recovered original per-section predictions; do not count them as failures or successes.

The population-specific confusion matrices, source hashes and exact case provenance are in scoring.v1.json. Section-level results are in scoring.v1.csv. The original proposed review packet and archived outputs remain unchanged.

## Validation

Source/case identity, exact section sets, archived model/prompt diagnostics and frozen label/source hashes were checked before scoring. Git LF/CRLF checkout differences are permitted for text hashes; other content changes are rejected. CSV confusion counts were independently recalculated and matched all population results. Existing measurement tests: 7 passed with a workspace-local temporary directory (the default Windows temporary directory was inaccessible). No application CI or model evaluation was rerun.
