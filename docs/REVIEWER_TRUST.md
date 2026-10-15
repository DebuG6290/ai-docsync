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
