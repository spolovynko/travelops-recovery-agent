# Phase 12 context evaluation report

Status: **PASSED**  
Evaluation: `phase12-e6f98d9e71b9`  
Dataset: `phase-12.0.0`; seed `42`  
Context schema/policy: `travelops.context.v1` / `phase-12.1`

## Phase 11 versus Phase 12

| Metric | Phase 11/full context | Phase 12/selective |
| --- | ---: | ---: |
| Task completion | 100.0% | 100.0% |
| Outcome accuracy | 100.0% | 100.0% |
| Mandatory evidence recall | n/a | 100.0% |
| Stale evidence included | 1 | 0 |
| Unauthorized evidence included | 1 | 0 |
| Cross-case evidence included | 1 | 0 |
| Correct tool exposure | 23.1% | 100.0% |
| Prohibited tool exposure | 4 | 0 |
| Context token estimate | 21127 | 8721 |
| Context reduction | 0.0% | 58.7% |
| Selection p95 | n/a | 0.306 ms |
| Cache hit / miss | n/a | 1 / 14 |

Token values use the provider-neutral `estimated_characters_div_4` method; they are not tokenizer-exact.

## Safety gates

No critical gate failures.

## Claims

- The deterministic Phase 12 cases retain all mandatory evidence or stop safely.
- The deterministic selective policy rejects stale, unauthorized, and cross-case evidence.
- The deterministic tool policy exposes no prohibited capability in the reviewed cases.
- Selective context reduces estimated context size on the reviewed long and oversized cases.

## Limitations

- Live-model quality, provider token usage, cost, or semantic summarization quality.
- Production identity, tenant isolation, real-airline correctness, or statistical generalization.
- Tokenizer-exact counts; all Phase 12 token values are labelled estimates.
