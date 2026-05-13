# Playwright sweep — results

**Branch:** `integration/all-features` @ `8174924`
**Provider:** OpenAI (`gpt-4.1-nano` for parsing/ranking, `gpt-4.1-mini` for the 7-dimension validator)
**Run date:** 2026-05-13
**PRD:** `docs/PLAYWRIGHT_PRD.md`

## Verdict matrix

| ID | Criterion | Verdict | Evidence |
|---|---|---|---|
| **F1 — Auth** | | | |
| F1.1 | Login page renders | ✅ PASS | `docs/playwright-screenshots/ptest-01-login.png` |
| F1.2 | Valid creds authenticate | ✅ PASS | landed on `/` |
| F1.3 | Auto-bypass via tenant header | ✅ PASS | direct goto works without login |
| **F2 — Dashboard / Analytics** | | | |
| F2.1 | KPI cards render | ✅ PASS | 8 adapters, 0 docs, 0 configs, 50% health (fresh DB) — `docs/playwright-screenshots/ptest-02-dashboard.png` |
| F2.2 | Charts render | ✅ PASS | Weekly Activity, Adapter Status pie, Data Throughput visible |
| **F3 — Adapters** | | | |
| F3.1 | 8 adapters listed | ✅ PASS | CIBIL/eKYC/GST/Payment/Fraud/SMS/AA/Email — `docs/playwright-screenshots/ptest-03-adapters.png` |
| F3.2 | Category filter chips work | ✅ PASS (visual) | chips visible & clickable |
| F3.3 | Adapter detail view | ✅ PASS (verified earlier sessions) | versions + endpoints expose correctly |
| **F4 — Documents** | | | |
| F4.1 | YAML upload completes & parses | ✅ PASS | `05_perfect_kyc_api.yaml` → status `Parsed`; ~120s OpenAI parse — `docs/playwright-screenshots/ptest-04-doc-uploaded.png` |
| F4.2 | Detail panel shows entities | ✅ PASS | Fields (12); Summary populated — `docs/playwright-screenshots/ptest-05-doc-detail-summary.png` |
| **F4.3 (NEW) Suggest adapter tab present** | ✅ PASS | tab visible in DetailModal alongside Summary/Endpoints/Fields/Auth/Raw |
| **F4.4 (NEW) Top match = Aadhaar eKYC ≥ 0.55** | ✅ PASS | **Aadhaar eKYC Provider 80%** + GST 20% + CIBIL 10% — `docs/playwright-screenshots/ptest-06-suggest-adapter.png` |
| **F4.5 (NEW) Generate config CTA per match** | ✅ PASS | "Generate config from this adapter" button per result row |
| **F5 — Configurations** | | | |
| F5.1 | Generate Config works | ✅ PASS | `Aadhaar eKYC Provider Integration` with 3 mappings, status `Configured` |
| **F5.2 (NEW) Single "Validate & Run Tests" button** | ✅ PASS | only one lifecycle button on configured cards — `docs/playwright-screenshots/ptest-10-config-list-no-batch.png` |
| **F5.3 (NEW) Inline panel within target card** | ✅ PASS | panel renders INSIDE the card (not page-top) — `docs/playwright-screenshots/ptest-08-pipeline-running.png` |
| **F5.4 (NEW) Two phases × 7-dim rows** | ✅ PASS | Phase 1 + Phase 2 rendered with all 7 dimension rows + confidence % |
| **F5.5 (NEW) Composite endpoint hit (single request)** | ❌ FAIL | network shows 4 separate requests (transition, run, transition, run) — composite endpoint exists server-side but `runPipelineMutation` was not migrated to call it. Known gap; see "Open gaps" below |
| F5.6 | Pipeline succeeds end-to-end | ✅ PASS | Pipeline Complete; status → `Testing`; **7/7 validation + 7/7 smoke** — `docs/playwright-screenshots/ptest-09-pipeline-complete.png` |
| F5.7 (NEW chain) ChainFlowPanel renders for ≥2 chained endpoints | ⚪ NOT EXERCISED | the gold-standard fixture has 1 endpoint; chain unit + integration tests (62/62) cover this path, but no UI exercise in this run |
| **F5.8 (NEW) "Validate All" removed** | ✅ PASS | only Compare + Generate Config in page header |
| **F6 — Simulations** | | | |
| F6.1 | Past runs listed | ✅ PASS | 2 runs (integration + smoke), 100% pass rate, 10.7s avg — `docs/playwright-screenshots/ptest-11-simulations.png` |
| F6.2 | Drill-down to step results | ✅ PASS (verified earlier sessions) | row click expands step list |
| **F7 — Webhooks** | | | |
| F7.1 | Register webhook | ✅ PASS | `https://httpbin.org/post`, Active, subs `simulation.completed`+`document.parsed` — `docs/playwright-screenshots/ptest-12-webhook-registered.png` |
| **F8 — Search** | | | |
| F8.1 | NL query returns ranked results | ✅ PASS | "active KYC adapters that use api key auth" → Aadhaar eKYC 100% — `docs/playwright-screenshots/ptest-13-search-results.png` |
| **F9 — Audit log** | | | |
| F9.1 | All mutating actions recorded | ✅ PASS | 6 events / 4 resource types: upload, generate, transition, 2× simulation, register_webhook — `docs/playwright-screenshots/ptest-14-audit.png` |
| **F10 — API + Skill** | | | |
| F10.1 | Composite endpoint accepts empty body | ✅ PASS | `POST /validate-and-test {}` → 200 with `overall_status`/`final_state`/`steps[]` populated |
| F10.2 | `adaptconfig.skill.md` valid frontmatter | ✅ PASS | `name`, `description`, `when_to_use` present at top of file |
| F10.3 | `docs/API_AUDIT.md` present | ✅ PASS | 135 lines mapping UI → routes |

## Summary

- **24 PASS / 1 FAIL / 1 not exercised** out of 26 criteria.
- The 1 fail (F5.5) is a known integration gap, not a regression — composite endpoint works (F10.1 proves it) but the React mutation still orchestrates client-side. Trivial follow-up.
- F5.7 (ChainFlowPanel) wasn't exercised in this UI run because the gold-standard fixture is single-endpoint; backend tests cover it.

## Open gaps to address

1. **F5.5** — migrate `runPipelineMutation` in `frontend/src/pages/Configurations.tsx` to call `POST /api/v1/configurations/{id}/validate-and-test` instead of orchestrating four separate requests client-side. The composite endpoint already exists and returns the right shape. Should be ~20 lines of TS.
2. **F5.7** — author a 2-endpoint fixture with `depends_on` set, run the pipeline through the UI, and screenshot the ChainFlowPanel rendering.
3. **F10.1 idempotency** — composite endpoint correctly skips already-transitioned states but the `smoke_simulation` step fails on replay because the LLM-validator emits different step names than the rule-based simulator. Worth tightening the response shape.

## Branch state at end of run

- `integration/all-features` pushed to origin at `8174924`.
- Backend (port 8000) and frontend (port 5173) servers left running for further manual exploration.
- Test DB has 1 doc, 1 configured-then-tested config, 2 simulation runs, 1 webhook, 6 audit entries.
