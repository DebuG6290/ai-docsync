# Reviewer trust and change visibility

## Version-specific evidence

The review text and its evidence come from the same persisted proposal version.
For accepted or published proposals, the displayed version is the exact
`accepted_version_id`; a newer row cannot replace the approved text in the UI.
Missing approved versions produce an error instead of showing different text.

Evidence completeness, missing information, code evidence and model claim lists
come from that version. Empty/legacy fields remain explicitly unrecorded; they do
not inherit the initial assessment. Human edits have no automatic model factual
assessment. Initial section evidence and impact rationale remain available as
clearly identified historical context.

Claim lists are labelled as model assessments, never independent human support
labels. Approve/Edit/Request revision still use existing workflow services and
immutable version IDs; this display change grants no approval or activation.

The archived HTTPX labels, scoring artifacts and proposal review packets are not
modified by these product changes. No production analysis or model evaluation is
required to test the UI: the regression tests use persisted synthetic test records.

## Mapping health

Reviews list changed symbols without an approved mapping as **not assessed** and
link to the existing Settings mapping flow. These warnings describe the saved
case scope; they do not change a section's UPDATE/NO_CHANGE/UNCERTAIN judgement or
retroactively rerun analysis. Deleted mapped symbols remain analysis candidates.

Settings → Mappings checks missing symbols and headings only within successfully
inspected files at the selected snapshot commit. Files with unsupported Python
syntax and relationships outside the inspection remain unchecked. Empty inspected
files still establish scope. No current branch-tip fetch or model call is needed
to display health for a saved snapshot. Confirming a mapping remains an explicit
human action and never approves baseline knowledge.
