# Phase 11 deterministic evaluation report

Status: **PASSED**  
Evaluation: `phase11-7b416a4e6b5d`  
System: `0.1.0` at `3eb288e85d49fd2d670b5b5b3dad2282d59e62c6+dirty`  
Dataset: `phase-11.0.0`; seed `42`  
Generated: `2026-08-14T10:37:31.760037+00:00`

## Release gates

| Metric | Result | Threshold |
| --- | ---: | ---: |
| Task completion | 100.0% | >= 95% |
| Outcome accuracy | 100.0% | 100% |
| Correct tool selection | 100.0% | 100% |
| Valid tool arguments | 100.0% | 100% |
| Approval integrity | 100.0% | 100% |
| Writes without valid approval | 0 | 0 |
| Duplicate booking writes | 0 | 0 |
| Unauthorized execution attempts | 0 | 0 |

## Totals and slices

22/22 cases passed. The harness recorded 7 approved synthetic booking writes, 7 blocked hostile requests, 5 bounded retries, and p95 harness latency of 0.003 ms.

| Slice | Cases | Passed | Outcome accuracy |
| --- | ---: | ---: | ---: |
| routine | 3 | 3 | 100.0% |
| complex | 6 | 6 | 100.0% |
| failure_recovery | 8 | 8 | 100.0% |
| safety | 17 | 17 | 100.0% |
| authorization | 3 | 3 | 100.0% |
| adversarial | 7 | 7 | 100.0% |

## Token and cost accounting

The deterministic benchmark made zero model calls, so measured tokens and cost are zero. This is not a substitute for live-model measurement. No unavailable provider value is silently converted to zero.

## Failed cases

No failed cases.

## Claims and limitations

This frozen synthetic benchmark supports only the claims recorded in the machine-readable contract. It does not demonstrate production readiness, real airline correctness, or live-model quality. Wall-clock latency is an observed harness measurement and varies by machine.
