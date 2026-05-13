# AdaptConfig — Playwright Test PRD

> Test matrix for the `integration/all-features` branch. Every feature has
> explicit Pass criteria, the Playwright steps that exercise it, and a
> Screenshot key for evidence. The headless run produces a markdown report
> mapping each criterion to PASS / FAIL.

**Branch under test:** `integration/all-features` (off `old-adaptconfig`).
**Provider:** OpenAI, model `gpt-4.1-nano` (parse + ranking), `gpt-4.1-mini`
(7-dimension validation). Set in `.env`.
**Base URLs:** http://127.0.0.1:8000 (backend), http://localhost:5173 (frontend).
**Admin login:** `admin@finspark.dev / Admin1234!` — note that the April-10
React app sends `X-Tenant-Role: admin` automatically, so the form login is
optional for most flows.

---

## F1 — Auth

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F1.1 | Login page renders | `goto /` → unauthed redirect to `/login` | Login form visible, fields and Sign In button enumerated |
| F1.2 | Valid credentials authenticate | Fill email + password, click Sign in | Browser lands on `/` dashboard |
| F1.3 | Auto-bypass via tenant header (April-10 quirk) | Direct `goto /` after fresh load | Dashboard renders without a login round trip |

## F2 — Dashboard / Analytics

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F2.1 | KPI cards render with seed values | `goto /` | Active Adapters = 8; Documents, Configurations, Health Score visible |
| F2.2 | Charts render | Same | Weekly Activity bar chart, Adapter Status pie chart, Data Throughput line chart all visible |

## F3 — Adapters

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F3.1 | Catalogue lists 8 adapters | `goto /adapters` | All 8 seeded adapter cards visible (CIBIL, eKYC, GST, Payment, Fraud, SMS, AA, Email) |
| F3.2 | Category filter chips work | Click `Bureau` chip | Only CIBIL card shown |
| F3.3 | Adapter detail view | Click CIBIL card | Versions + endpoints visible |

## F4 — Documents

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F4.1 | Upload YAML completes within 60s | `goto /documents` → upload `test_fixtures/05_perfect_kyc_api.yaml` | Row appears with status `Parsed` |
| F4.2 | Detail panel shows extracted entities | Click parsed row | Summary tab populated; Endpoints ≥1; Fields ≥6 |
| F4.3 | **(NEW)** Suggest adapter tab exists | Open detail panel | A tab labelled "Suggest adapter" is present |
| F4.4 | **(NEW)** Suggest adapter returns ranked matches | Click Suggest adapter tab → click suggest button | Top result is `Aadhaar eKYC Provider` with ≥ 0.55 match (≥ 0.85 ideal) |
| F4.5 | **(NEW)** Suggest adapter offers "Generate config" CTA | After F4.4 | Each match row has a `Generate config from this adapter` button |

## F5 — Configurations

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F5.1 | Generate Config form works | Click `Generate Config` → pick parsed doc + Aadhaar eKYC + version | Card with status `Configured` and ≥ 3 field mappings appears |
| F5.2 | **(NEW)** Single button labelled "Validate & Run Tests" replaces former two-step | Look at `configured`-state card actions | Only one lifecycle button, labelled `Validate & Run Tests` |
| F5.3 | **(NEW)** Pipeline panel renders **inline** within the specific card | Click `Validate & Run Tests` | Progress panel appears INSIDE the target card (not at page top) |
| F5.4 | **(NEW)** Panel shows two phases (Validation + Smoke) with per-step rows | Watch the panel | 7 validation-dimension rows with confidence %, then 4 smoke rows |
| F5.5 | **(NEW)** Composite endpoint is hit (single round-trip server-side) | Network panel filter `/api/v1` | A single `POST /api/v1/configurations/{id}/validate-and-test` request (instead of multiple transition + run calls) |
| F5.6 | Pipeline succeeds end-to-end with the gold-standard fixture | After F5.3 | Panel header reads `Pipeline Complete`; card status moves to `Testing` |
| F5.7 | **(NEW — chain runtime)** ChainFlowPanel renders for configs with ≥2 chained endpoints | Generate a config that produces 2+ endpoints with `depends_on` | Vertical `[A] → [B]` flow visible in the expanded card with extract/inject pairs |
| F5.8 | "Validate All" batch button is gone | Inspect page header | No `Validate All` button anywhere; only `Generate Config` and (if ≥2 configs) `Compare` remain |

## F6 — Simulations

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F6.1 | Simulations page lists past runs | `goto /simulations` | Run from F5.6 appears with steps count + pass-rate |
| F6.2 | Drill-down to step results | Click row | Step list with confidence + analysis text |

## F7 — Webhooks

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F7.1 | Register a webhook | `goto /webhooks` → Add Webhook → fill URL + secret + 3 events → Create | Row appears Active |

## F8 — Search

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F8.1 | Natural-language query returns ranked results | `goto /search` → type `active KYC adapters that use api key auth` | Aadhaar eKYC Provider listed at ≥ 80% relevance |

## F9 — Audit log

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F9.1 | Audit log records all mutating actions | `goto /audit` after F1–F7 | Entries for upload, generate, transition, simulation, register_webhook visible |

## F10 — API surface (out-of-browser, but verified once via curl)

| ID | Criterion | Steps | Pass when |
|---|---|---|---|
| F10.1 | Composite endpoint accepts an empty body | curl `POST /api/v1/configurations/{id}/validate-and-test` with `{}` | 200 with `overall_status` field populated |
| F10.2 | Skill file is valid markdown with frontmatter | inspect `adaptconfig.skill.md` | Starts with `---` frontmatter block including `name`, `description` |
| F10.3 | API_AUDIT.md exists | inspect `docs/API_AUDIT.md` | File present with page → route mapping |

---

## Screenshots written by the run

All under repo root with prefix `ptest-`:
- `ptest-01-login.png` — F1.1
- `ptest-02-dashboard.png` — F2.1, F2.2
- `ptest-03-adapters.png` — F3.1, F3.2
- `ptest-04-doc-uploaded.png` — F4.1
- `ptest-05-doc-detail-summary.png` — F4.2
- `ptest-06-suggest-adapter.png` — F4.3, F4.4, F4.5
- `ptest-07-config-generated.png` — F5.1
- `ptest-08-pipeline-running.png` — F5.2, F5.3, F5.4
- `ptest-09-pipeline-complete.png` — F5.5, F5.6
- `ptest-10-config-list-no-batch.png` — F5.8
- `ptest-11-simulations.png` — F6.1, F6.2
- `ptest-12-webhook-registered.png` — F7.1
- `ptest-13-search-results.png` — F8.1
- `ptest-14-audit.png` — F9.1

Final report: see `docs/PLAYWRIGHT_RESULTS.md`.
