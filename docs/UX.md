# DocSync review workspace

## Product decisions

The documentation owner is the primary user. Home answers what needs attention; Reviews answers what changed and what should be approved; Knowledge answers which approved snapshot Chat can use. History preserves decisions and operation milestones. Settings keeps setup information secondary.

The visual system uses a light canvas, white cards, restrained blue actions, green approvals, amber uncertainty, red failures and neutral historical states. Labels accompany colors. Evidence and technical identifiers stay available behind disclosure controls. Narrow screens wrap comparison columns and section navigation.

## Review contract

- Inspect one section at a time, with the changed text and rationale visible.
- Approve the exact displayed version.
- Saving an edit creates a human version; approval is a separate action.
- Request a targeted revision with a reason.
- Resolve uncertainty with a recorded human reason.
- Override NO_CHANGE with human text and a reason before publication starts, then approve separately.
- Preserve the original model assessment and every version/action in history.

## Architecture

`streamlit_app.py` handles authentication, database initialization, navigation and bounded session refresh. `docsync/ui/` contains page components, shared styling and read models. Existing workflow services perform mutations; the frozen Phase 1 engine and Sarvam reasoning contract remain unchanged.

Release states distinguish prepared publication, waiting for merge, confirmed merge, verification, indexing, activation and recoverable failures. Additive Alembic migration 003 persists milestones. Public GitHub reconciliation confirms only the identity of known approved releases; verified indexing is still required to activate knowledge. Approved-only retrieval and atomic activation remain unchanged.

## Validation and deployment

Automated coverage includes all page navigation, editor drafts across navigation, separate human save/approval, NO_CHANGE overrides, publication boundaries, explicit lifecycle states and idempotent merge reconciliation. Local screenshots use synthetic sample cases and disabled model calls. Hosted acceptance requires checking the deployed UI against the real database and indexing workflow.

Deploy the main branch Streamlit entry point and update both HTTPX reusable-workflow and checkout pins together to the reviewed application release. Existing caller pins may run older indexing code and therefore omit new lifecycle milestones. No paid hosting, permanent worker or reasoning prompt tuning is introduced.
