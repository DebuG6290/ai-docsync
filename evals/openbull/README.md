# OpenBull evidence preparation

`conflict-candidate.json` captures public lifecycle-description excerpts at a fixed
commit. It is a candidate-narrowing regression fixture, not an adjudicated conflict
accuracy case. Classification is intentionally unlabelled until a human reviews
the actual scopes, versions and source authority. Preserve that distinction when
promoting the fixture to the benchmark.

Before Batch 2 mutates the validation fork, deploy the reviewed conflict gate and
inspect the actual repository-scoped approved mappings/knowledge. Audit the active
baseline for lifecycle conflicts. The local checkout has no production database
configuration, so mappings and active text cannot be inferred from public filenames.

Current inspected commit: `00673ebb95a8c08cd5523f6e5f7f6e196eaa47b9`.
`backend/services/trading_mode_service.py::dispatch_by_mode` currently routes sandbox
without a supplied sandbox callback to the live callback. The general architecture
description says sandbox routes to the simulated engine. This is useful evidence
for a routing-impact case, but changing the fallback needs to be tied to verified
approved mappings and a pre-recorded case; no arbitrary fork change has been made.

Record the frozen before/after pair, mapped impacted/non-impacted sections, safe and
forbidden claims, expected conflict pairs and label provenance before analysis.
Do not report the preparatory inspection as a completed OpenBull lifecycle.
