# Phase 1.1 Held-out Labels (Frozen Before Sarvam Calls)

These expected labels were adjudicated from the controlled old/new code and documentation fixtures using the section-level definitions in the evaluation request. The expected labels are not included in the model input. `COMPLETE`, `PARTIAL`, and `INSUFFICIENT` describe evidence completeness; they do not determine the section decision.

| Case | Expected decision | Completeness | Label rationale |
|---|---|---|---|
| H1 | UPDATE | COMPLETE | The full new helper visibly strips outer whitespace and title-cases its input, contradicting the “exactly as received” documentation. Both transformations are safe replacement claims. |
| H2 | UPDATE | COMPLETE | The complete function changes its returned literal from `v1` to `v2`; the documented default is stale. No downstream protocol behavior is needed to state the changed literal. |
| H3 | NO_CHANGE | COMPLETE | Complete old and new implementations both strip outer whitespace and lowercase in the same order. The documented behavior remains accurate. |
| H4 | NO_CHANGE | COMPLETE | Both complete function bodies return integer `3`; assigning the literal to a local variable does not change the documented result. |
| H5 | UNCERTAIN | INSUFFICIENT | The old active-field rule may still be what the unavailable policy implements. The delegation call is known, but replacing the user-facing eligibility rule with only an implementation-call description would not resolve whether the current behavior remains accurate. Missing: the policy implementation/rule and whether it still uses the active-field criterion. |
| H6 | UPDATE | PARTIAL | The old fixed-count documentation is contradicted by the new direct read of `deployment_config['workers']`. A useful replacement can state that the count comes from that configuration key. The active value and missing-key/default behavior are unavailable and must not be invented. |
| H7 | UPDATE | PARTIAL | The old exact status-code rule is replaced by a direct delegation to `client.retry_provider.is_retryable(response)`. Documenting that delegation is useful and supported. The provider's classification policy is unavailable; no status-code rule may be asserted. |
| H8 | UNCERTAIN | INSUFFICIENT | The unavailable manager may still open a direct TCP socket, so the existing transport claim is not demonstrably stale. A delegation-only replacement would not answer the user-facing transport question. |
| H9 | UPDATE | PARTIAL | The old fixed 30-day statement is contradicted by reading and converting `RETENTION_DAYS`. A useful replacement can state that the value is environment-driven. Its active value and behavior when absent are unavailable. |
| H10 | UNCERTAIN | INSUFFICIENT | The documented HTTP/2 preference may remain true or may have changed under an unavailable runtime profile. Naming the delegation would not answer the documented protocol preference question. |
| H11 | UNCERTAIN | INSUFFICIENT | The unavailable crypto provider may preserve or alter the sensitive-record encryption policy. Naming the provider call would not establish the user-facing encryption guarantee. |

## Frozen claim boundaries

- H1: safe claims are outer-whitespace stripping and title-casing. No unavailable behavior is relevant.
- H2: safe claim is that `protocol_version()` returns literal `v2`; do not generalize to every protocol implementation.
- H3: safe claims are outer-whitespace stripping followed by lowercasing.
- H4: safe claim is that `max_attempts()` returns integer `3`.
- H5: safe claim is delegation to `eligibility_policy.allows(item)`. Unsupported claims are that the new policy still checks only `active` or that `active=true` guarantees eligibility.
- H6: safe claim is reading and returning `deployment_config['workers']`. Unsupported claims include any specific runtime count or default.
- H7: safe claim is delegation to the configured retry provider. Unsupported claims include the old `408`, `429`, and `5xx` set or any other exact provider policy.
- H8: safe claim is delegation to `session_manager.open(host)`. Unsupported claims include direct TCP, TLS, pooling, or other manager behavior; the old direct-TCP documentation may still be correct, so delegation alone is not a useful replacement.
- H9: safe claim is reading `RETENTION_DAYS` and converting it to an integer. Unsupported claims include a 30-day runtime value or unset-variable default.
- H10: safe claim is delegation to `runtime_profile.alpn_protocols(supported_protocols)`. Unsupported claims include any exact protocol preference or ordering.
- H11: safe claim is delegation to `crypto_provider.requires_encryption(record)`. Unsupported claims include which records are encrypted or whether encryption happens before storage.

The set contains five UPDATE cases (H1, H2, H6, H7, H9), two NO_CHANGE cases (H3-H4), and four UNCERTAIN cases (H5, H8, H10-H11). H6, H7, and H9 deliberately test partial evidence with a useful bounded update. H5, H8, H10, and H11 test distinct reasons why unavailable policy behavior prevents determining whether the current user-facing claim remains accurate.
