# Business Requirements Document
## Credit Bureau Integration — CIBIL TransUnion
**Document ID:** BRD-INT-2024-047
**Version:** 2.3
**Status:** Approved
**Prepared By:** Integration Architecture Team
**Reviewed By:** CTO, Chief Risk Officer, CISO
**Approval Date:** 2024-11-15
**Effective Date:** 2025-01-01

---

## 1. Project Overview

### 1.1 Purpose

FinSpark Lending Platform requires a certified integration with CIBIL TransUnion's Credit Information Bureau to enable automated credit decisioning for retail and MSME loan origination workflows. This document specifies the functional, non-functional, and compliance requirements for this integration.

The integration will replace the current manual bureau pull process (average TAT: 4 hours) with a real-time automated decisioning pipeline (target TAT: sub-5 seconds), directly embedded into the loan application workflow managed by the Loan Origination System (LOS).

### 1.2 Business Objectives

- **BO-01:** Reduce credit underwriting TAT from 4 hours to under 10 seconds for individual applicants.
- **BO-02:** Enable straight-through processing (STP) for pre-approved loan products with bureau score ≥ 720.
- **BO-03:** Support bulk overnight bureau refresh for portfolio monitoring (up to 50,000 accounts/night).
- **BO-04:** Maintain full DPDP Act 2023 compliance for PII data handling and consent management.
- **BO-05:** Achieve RBI Master Direction on Digital Lending compliance for credit information usage.

### 1.3 Scope

**In Scope:**
- Real-time credit score inquiry for individual applicants (retail lending)
- Full CIBIL report pull for underwriting decisions above INR 5 lakhs
- Bulk bureau inquiry for portfolio monitoring and early warning system (EWS)
- Adverse action reason code parsing and mapping to internal decision codes
- Consent management lifecycle (capture → bureau → audit trail)
- Integration with FinSpark's existing Vault service for credential management

**Out of Scope:**
- Commercial bureau integration (CRIF High Mark for business entities — covered under BRD-INT-2024-051)
- Equifax / Experian bureau integrations (Phase 2)
- Dispute management workflow with bureau
- Bureau data enrichment for marketing purposes

### 1.4 Stakeholders

| Role | Name | Responsibility |
|------|------|----------------|
| Product Owner | Priya Sharma | Feature acceptance, priority decisions |
| Integration Architect | Rajesh Nair | Technical design, API contracts |
| Risk Analytics | Amit Verma | Score interpretation, cutoff calibration |
| Information Security | Deepa Krishnan | PII handling, encryption standards |
| Compliance | Sunita Mehta | RBI/DPDP regulatory sign-off |
| CIBIL Relationship Manager | Vikram Joshi | Bureau-side configuration, SLA escalation |

---

## 2. Integration Requirements

### 2.1 API Endpoints

The integration will consume three CIBIL TransUnion API endpoints from the CIBIL CreditVision® API Suite v2.1. All endpoints are served over HTTPS on base URL `https://api.cibil.com/creditvision/v2`.

#### 2.1.1 Credit Score Inquiry Endpoint

**Endpoint:** `POST /score/inquiry`
**Purpose:** Retrieves the CIBIL Score (range 300–900) and a brief score summary for a single individual applicant. This is the primary call in the pre-qualification stage and must complete within the LOS decisioning SLA window.

**Trigger Conditions:**
- Applicant submits a loan application in FinSpark LOS
- Existing borrower triggers a credit limit enhancement request
- Risk team initiates a manual score refresh from the borrower 360 view

**Request Content-Type:** `application/json`
**Response Content-Type:** `application/json`
**Idempotency:** Supported via `X-Idempotency-Key` header (UUID v4). Duplicate requests within a 60-second window return cached response without generating a new bureau hit.

#### 2.1.2 Full Credit Report Endpoint

**Endpoint:** `POST /report/pull`
**Purpose:** Retrieves the complete CIBIL Credit Information Report (CIR) including account history, enquiry history, public records, and DPD (Days Past Due) grid for all reported accounts. Used for full underwriting of applications above INR 5 lakhs and for loan accounts flagged as high-risk by FinSpark's internal scoring model.

**Trigger Conditions:**
- Loan application amount ≥ INR 5,00,000
- Internal risk score below threshold (configurable per product: default 640)
- Underwriter manually requests full report from LOS workbench
- Credit committee review for structured/complex credit facilities

**Request Content-Type:** `application/json`
**Response Content-Type:** `application/json`
**Report Format:** CIBIL CIR JSON v2.1 (not the legacy XML format)
**Pagination:** Full report is returned in a single response. Reports exceeding 512 KB trigger an async generation flow — see Section 2.5.

#### 2.1.3 Bulk Inquiry Endpoint

**Endpoint:** `POST /inquiry/bulk`
**Purpose:** Submits a batch of up to 5,000 PAN numbers per request for overnight portfolio monitoring. Responses are delivered asynchronously via a webhook callback registered at integration setup time. Used by the Early Warning System (EWS) and the Collections Risk Engine.

**Trigger Conditions:**
- Scheduled nightly job (02:00–04:00 IST window, configurable)
- EWS triggers batch refresh for accounts entering 30+ DPD bucket
- Collections team uploads manual watch-list via LOS admin panel

**Request Content-Type:** `application/json`
**Response Model:** Asynchronous. HTTP 202 Accepted on submission. Results delivered to webhook within 4 hours of submission for batches up to 5,000 records.
**Webhook URL (FinSpark):** `https://api.finspark.in/webhooks/bureau/bulk-results`

### 2.2 Field Mappings

All field names and data types below are normative. Deviation requires sign-off from the Integration Architect.

#### 2.2.1 Score Inquiry Request Field Mapping

| FinSpark Internal Field | CIBIL API Request Field | Type | Format / Constraint | Required |
|-------------------------|------------------------|------|---------------------|----------|
| `applicant.full_name` | `ConsumerName.FirstName` + `ConsumerName.LastName` | string | Split on last whitespace; max 100 chars each | Yes |
| `applicant.pan_number` | `IDDetails[].IDValue` where `IDType = "PAN"` | string | Regex: `[A-Z]{5}[0-9]{4}[A-Z]{1}` | Yes |
| `applicant.date_of_birth` | `DateOfBirth` | string | ISO 8601: `YYYY-MM-DD` | Yes |
| `applicant.mobile_number` | `PhoneNumbers[].Number` where `PhoneType = "MOBILE"` | string | 10 digits, no country code | Conditional |
| `applicant.address.line1` | `Addresses[].AddressLine1` | string | Max 100 chars | Yes |
| `applicant.address.line2` | `Addresses[].AddressLine2` | string | Max 100 chars | No |
| `applicant.address.city` | `Addresses[].City` | string | Max 50 chars | Yes |
| `applicant.address.state_code` | `Addresses[].State` | string | 2-char ISO 3166-2:IN state code | Yes |
| `applicant.address.pincode` | `Addresses[].PostalCode` | string | 6-digit numeric | Yes |
| `applicant.gender` | `Gender` | string | Enum: `"M"`, `"F"`, `"T"` | No |
| `application.id` | `MemberReferenceNumber` | string | Max 30 chars; use FinSpark app UUID (first 30 chars) | Yes |
| `product.bureau_product_code` | `ProductType` | string | Enum: `"INDV-SCR"` for score-only | Yes |

**Name Splitting Logic:**
`ConsumerName.FirstName` = all tokens except the last; `ConsumerName.LastName` = last token. For single-token names, `FirstName = ""` and `LastName` = the full name.

**PAN Validation:**
PAN must be validated locally before dispatch using regex `^[A-Z]{5}[0-9]{4}[A-Z]{1}$`. Invalid PAN must return a FinSpark error code `ERR_BUREAU_PAN_INVALID` without making a bureau API call.

**State Code Mapping:**
Map FinSpark's full state names to 2-char codes using the internal reference table `ref_state_codes` in the configuration database. Unmapped states fall back to `XX` and trigger a warning log entry.

#### 2.2.2 Full Report Request Field Mapping

Full report request uses all fields from Section 2.2.1, plus:

| FinSpark Internal Field | CIBIL API Request Field | Type | Format / Constraint | Required |
|-------------------------|------------------------|------|---------------------|----------|
| `applicant.email` | `EmailContacts[].EmailID` | string | RFC 5322 format; max 80 chars | No |
| `application.loan_amount` | `EnquiryAmount` | integer | Amount in INR paise (multiply rupees × 100) | Yes |
| `product.loan_type_code` | `EnquiryPurpose` | string | See Appendix A for CIBIL purpose code mapping | Yes |
| `underwriter.employee_id` | `MemberUserID` | string | Max 20 chars | Yes |
| `product.bureau_product_code` | `ProductType` | string | `"INDV-CIR"` for full report | Yes |

#### 2.2.3 Bulk Inquiry Request Field Mapping

| FinSpark Internal Field | CIBIL API Request Field | Type | Format / Constraint | Required |
|-------------------------|------------------------|------|---------------------|----------|
| `batch.id` | `BatchReferenceNumber` | string | UUID v4, max 36 chars | Yes |
| `batch.records[].pan_number` | `Inquiries[].IDValue` | string | PAN; same validation as 2.2.1 | Yes |
| `batch.records[].applicant_name` | `Inquiries[].ConsumerName` | string | Full name, max 100 chars | Yes |
| `batch.records[].date_of_birth` | `Inquiries[].DateOfBirth` | string | ISO 8601: `YYYY-MM-DD` | Yes |
| `batch.records[].loan_account_id` | `Inquiries[].MemberReferenceNumber` | string | FinSpark loan account ID, max 30 chars | Yes |
| `batch.callback_url` | `CallbackURL` | string | Must match pre-registered URL; see Section 2.1.3 | Yes |
| `batch.notification_email` | `NotificationEmail` | string | Ops team DL: `bureau-ops@finspark.in` | No |

#### 2.2.4 Score Response Field Mapping (CIBIL → FinSpark)

| CIBIL API Response Field | FinSpark Internal Field | Type | Notes |
|--------------------------|------------------------|------|-------|
| `CIBILScore` | `bureau_result.score` | integer | 300–900; -1 if insufficient history; -2 if no history |
| `ScoreCardVersion` | `bureau_result.score_model_version` | string | e.g., `"V2"` |
| `ScoreReasonCodes[]` | `bureau_result.reason_codes[]` | array[string] | Up to 4 codes; map via Appendix B |
| `RequestID` | `bureau_result.bureau_reference_id` | string | Store for audit; never expose in API responses |
| `MemberReferenceNumber` | `bureau_result.member_reference` | string | Echo of request field; use for reconciliation |
| `EnquiryDateTime` | `bureau_result.enquiry_timestamp` | string | UTC ISO 8601; convert to IST for display |
| `SegmentType` | `bureau_result.consumer_segment` | string | `"INDIVIDUAL"` or `"NTC"` (New To Credit) |
| `BureauResponseCode` | `bureau_result.raw_response_code` | string | Store raw; see Section 6 for handling |

#### 2.2.5 Full Report Response Handling

The full CIR response is a complex nested JSON. Key extraction paths:

| CIBIL CIR Field Path | FinSpark Storage | Notes |
|---------------------|-----------------|-------|
| `CIRReportDataLst[0].CIRReportData.ScoreDetails[0].Value` | `cir.cibil_score` | Primary score |
| `CIRReportDataLst[0].CIRReportData.IDAndContactInfo.PersonalInfo.Name.FullName` | `cir.applicant_name_on_bureau` | For name mismatch checks |
| `CIRReportDataLst[0].CIRReportData.RetailAccountDetails[]` | `cir.trade_lines[]` | Full account history array |
| `CIRReportDataLst[0].CIRReportData.EnquiryDetails[]` | `cir.enquiry_history[]` | Last 24 months of hard pulls |
| `CIRReportDataLst[0].CIRReportData.PublicRecords[]` | `cir.public_records[]` | Defaults, write-offs, settlements |
| `CIRReportDataLst[0].CIRReportData.RetailAccountDetails[].PaymentHistory47` | `cir.dpd_grid` | 47-month DPD string |
| `Header.ReportDate` | `cir.report_date` | Report generation date |
| `Header.SubjectSegmentIndicator` | `cir.consumer_classification` | `I` = Individual, `C` = Commercial |

### 2.3 Authentication Requirements

#### 2.3.1 Authentication Architecture

CIBIL's API v2.1 uses a dual-layer authentication model combining API Key authentication with Mutual TLS (mTLS). Both layers must be satisfied for every request. Neither layer alone is sufficient.

**Layer 1 — API Key:**
- Header name: `X-CIBIL-API-Key`
- Value: A 64-character alphanumeric string issued per FinSpark member account
- Rotation schedule: Every 90 days, mandatory. CIBIL will disable keys older than 120 days without exception.
- Storage: HashiCorp Vault path `secret/integrations/credit-bureau/cibil/api-key` (KV v2 engine). The integration layer must use Vault's dynamic secret mechanism — API keys must never appear in application configuration files, environment variables, or logs.

**Layer 2 — Mutual TLS (mTLS):**
- FinSpark must present a client certificate signed by CIBIL's approved Certificate Authority (CA): `CIBIL-Member-CA-2024`
- Certificate format: X.509 v3, RSA-4096 minimum (ECDSA P-384 preferred)
- Certificate validity: 1 year. Renewal must be initiated at least 30 days before expiry.
- Certificate chain: Client certificate → CIBIL Intermediate CA → CIBIL Root CA (pinned in FinSpark TLS config)
- Certificate storage: Vault PKI secrets engine at `pki/integrations/cibil/`
- Private key: Must never leave Vault. The integration service must use Vault's `cert` auth method to obtain a short-lived token and retrieve the certificate for the TLS handshake.

**Layer 3 — Request Signing (required for bulk endpoint only):**
- Algorithm: HMAC-SHA256
- Signed headers: `X-CIBIL-API-Key`, `Content-Type`, `X-Request-Timestamp`, request body (SHA-256 hash)
- Signature header: `X-CIBIL-Signature`
- Timestamp tolerance: ±5 minutes. Requests outside this window are rejected with HTTP 401.

#### 2.3.2 Credential Management Workflow

1. Integration service starts → authenticates to HashiCorp Vault using Kubernetes service account token (k8s auth method).
2. Vault returns a short-lived Vault token (TTL: 15 minutes, renewable).
3. Service reads API key from `secret/integrations/credit-bureau/cibil/api-key`.
4. Service requests TLS certificate via Vault PKI engine; receives certificate + private key in-memory.
5. Service initializes HTTPS client with the mTLS certificate for the duration of the connection pool.
6. On Vault token expiry, step 1–5 is repeated automatically by the credentials refresh background task.

### 2.4 Response Handling

#### 2.4.1 Score Parsing

The CIBIL Score field `CIBILScore` must be interpreted as follows:

| Raw Value | Meaning | FinSpark Action |
|-----------|---------|-----------------|
| 300–900 | Valid CIBIL Score | Proceed to decisioning engine; pass score as-is |
| -1 | Insufficient credit history (< 6 months) | Flag as `NTC` (New To Credit); apply NTC policy |
| -2 | No credit history found | Flag as `NH` (No Hit); apply NH policy; do not reject automatically |
| 0 | Error in score computation | Treat as `BUREAU_ERROR`; route to manual underwriting |
| 999 | Consumer has opted for credit freeze | Reject with adverse action reason `ADV_001_CREDIT_FREEZE` |

#### 2.4.2 Report Generation and Storage

1. Full CIR JSON response is stored in encrypted form in FinSpark's document store (S3-compatible, encrypted at rest with AES-256-GCM using a per-tenant CMK).
2. A structured extract (trade lines, score, DPD grid, enquiry count) is written to the `credit_bureau_reports` PostgreSQL table for query/reporting.
3. The raw JSON is retained for 7 years per RBI guidelines. Structured data retained for the life of the loan + 2 years.
4. A report reference ID (`bureau_report_id`) is returned to the LOS and stored on the loan application record.

#### 2.4.3 Reason Code Mapping

CIBIL returns up to 4 score reason codes (R001–R099). Each code must be mapped to:
- A human-readable description for the underwriter UI
- An adverse action letter code if the application is declined (ECOA/Indian Credit Act compliance)
- An internal FinSpark remediation suggestion for customer communication

The mapping table is maintained in `config/bureau/cibil_reason_code_map.json` and is versioned alongside the integration configuration.

---

## 3. Data Flow

### 3.1 Real-Time Score Inquiry Flow

```
[LOS Applicant Submission]
        |
        v
[FinSpark API Gateway]
  - Rate limit check (per tenant)
  - JWT auth verification
        |
        v
[Bureau Integration Service]
  - Consent verification (check consent_events table)
  - PAN format validation
  - Name normalization (split, trim, uppercase)
  - Field mapping (Section 2.2.1)
  - Idempotency key generation (SHA-256 of PAN+DOB+AppID)
        |
        v
[Vault Credential Fetch]
  - API key retrieval
  - mTLS certificate retrieval
        |
        v
[CIBIL API POST /score/inquiry]
  - TLS 1.3 with mTLS
  - X-CIBIL-API-Key header
  - Timeout: 8 seconds (Section 5.1)
        |
        v
[Response Processing]
  - HTTP status check
  - BureauResponseCode parsing (Section 6)
  - Score extraction and interpretation (Section 2.4.1)
  - Reason code mapping (Section 2.4.3)
  - Audit event write (bureau_audit_log table)
        |
        v
[Return to LOS]
  - bureau_score, reason_codes[], bureau_reference_id
  - bureau_hit_type (HIT / NTC / NH / ERROR)
  - enquiry_timestamp
```

### 3.2 Full Report Pull Flow

```
[LOS Underwriting Trigger]
        |
        v
[Bureau Integration Service]
  - All steps from 3.1 flow, plus:
  - Loan amount → paise conversion
  - EnquiryPurpose code lookup
  - MemberUserID injection
        |
        v
[CIBIL API POST /report/pull]
  - Response size check: if > 512 KB, switch to async flow (Section 3.3)
        |
        v
[Synchronous Response (< 512 KB)]
  - CIR JSON extraction (Section 2.2.5 field paths)
  - Encrypt and upload to S3 (per-tenant CMK)
  - Write structured extract to credit_bureau_reports table
  - Generate bureau_report_id (UUID v4)
  - Write audit event
        |
        v
[Return bureau_report_id to LOS]
```

### 3.3 Async Report Flow (Large Reports > 512 KB)

```
[CIBIL returns HTTP 202 with report_token]
        |
        v
[Bureau Integration Service]
  - Store report_token in redis with TTL 1 hour
  - Enqueue polling job (exponential backoff: 5s, 10s, 20s, max 3 attempts)
        |
        v
[Polling: GET /report/status/{report_token}]
  - On COMPLETED: download report, process as synchronous flow
  - On PENDING: retry with backoff
  - On FAILED: trigger manual review alert; return ERR_BUREAU_REPORT_FAILED
```

### 3.4 Bulk Inquiry Flow

```
[EWS / Collections Scheduler]
        |
        v
[Bureau Integration Service]
  - Read account batch from portfolio_monitoring_queue
  - Chunk into batches of max 5,000 records
  - Generate batch_reference_number (UUID v4)
  - HMAC-SHA256 request signing
        |
        v
[CIBIL API POST /inquiry/bulk]
  - HTTP 202 Accepted → store batch job record
  - HTTP 4xx/5xx → retry logic (Section 6.3)
        |
        v
[Webhook Callback: POST /webhooks/bureau/bulk-results]
  - Validate CIBIL webhook signature (X-CIBIL-Webhook-Signature header)
  - Process each record result
  - Update portfolio_bureau_scores table
  - Trigger EWS rule engine for flagged accounts
  - Publish domain events to Kafka topic bureau.portfolio.refresh
```

### 3.5 Consent Management

Per DPDP Act 2023 and RBI guidelines, bureau pull is permitted only with explicit, informed, and granular consent. The integration service must:

1. Check `consent_records` table for a valid consent record for the applicant PAN before any bureau call.
2. Consent record must have `consent_type = "CREDIT_BUREAU"`, `status = "ACTIVE"`, and `valid_until > NOW()`.
3. If consent is absent or expired, the integration service must return `ERR_BUREAU_CONSENT_MISSING` to the LOS without making any bureau call.
4. Each bureau hit must write to `consent_usage_log` with: consent_id, bureau_call_type, bureau_reference_id, timestamp, calling_user_id.

---

## 4. Security Requirements

### 4.1 Encryption Requirements

**4.1.1 Transport Security**
- All communication with CIBIL API must use TLS 1.3. TLS 1.2 is permitted only as a fallback with explicit approval from the CISO.
- Cipher suites allowed: `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`. No RC4, DES, 3DES, or export ciphers.
- Certificate pinning: CIBIL's server certificate (leaf and intermediate) must be pinned in the integration service configuration. Pin rotation procedure must be tested in staging before production deployment.

**4.1.2 Data at Rest**
- Full CIR JSON stored in S3: encrypted with AES-256-GCM. Per-tenant Customer Managed Keys (CMK) in AWS KMS.
- Structured bureau data in PostgreSQL: column-level encryption for fields: `pan_number`, `date_of_birth`, `mobile_number`, `full_name` using `pgcrypto` with AES-256.
- Audit logs: immutable, append-only, encrypted. Write to a separate audit schema with no DELETE privilege granted to application roles.

**4.1.3 Key Management**
- CMKs must be rotated annually.
- Key rotation must not break decryption of existing records (envelope encryption pattern mandatory).
- KMS access logging must be enabled; any decryption event must generate an audit trail.

### 4.2 PII Handling

**4.2.1 Data Classification**
The following fields are classified as Sensitive Personal Information (SPI) under DPDP Act 2023:

| Field | Classification | Handling Requirement |
|-------|---------------|----------------------|
| PAN Number | SPI — Financial Identifier | Mask in logs as `XXXXX1234X`; encrypt at rest; never in query params |
| Date of Birth | SPI | Mask in logs as `****-**-DD`; encrypt at rest |
| Full Name | Personal Data | Mask surname in logs; encrypt at rest |
| Mobile Number | Personal Data | Mask as `XXXXXX1234` in logs; encrypt at rest |
| Credit Score | Financial Data | Do not log raw score at DEBUG level in production |
| Full CIR JSON | Highly Sensitive | No logging; encrypt immediately on receipt; access via signed URLs only |

**4.2.2 Data Minimization**
- Score-only inquiry must not request or store full CIR data.
- Bulk inquiry results must contain only score and reason codes — no full report.
- PAN numbers in bulk request files must be deleted from application memory immediately after batch submission.

**4.2.3 Data Residency**
All bureau data must reside in AWS ap-south-1 (Mumbai) region. No replication to non-Indian regions permitted.

**4.2.4 Data Retention and Deletion**
- Full CIR: 7 years from report date (RBI requirement)
- Bureau score records: Life of loan + 2 years
- Consent usage logs: 5 years
- On account closure + retention expiry: hard delete from S3 and PostgreSQL, with deletion certificate written to audit log

### 4.3 Audit Requirements

Every bureau interaction must produce an audit event written to the `bureau_audit_log` table with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | UUID | Primary key, auto-generated |
| `tenant_id` | UUID | Tenant making the request |
| `applicant_pan_hash` | string | SHA-256 of PAN (never store raw PAN in audit log) |
| `call_type` | enum | `SCORE_INQUIRY`, `REPORT_PULL`, `BULK_INQUIRY` |
| `trigger_source` | string | `LOS`, `EWS`, `COLLECTIONS`, `MANUAL` |
| `initiated_by_user_id` | UUID | User ID if manual; system service account ID if automated |
| `bureau_reference_id` | string | CIBIL's RequestID |
| `http_status_code` | integer | HTTP response status |
| `bureau_response_code` | string | CIBIL BureauResponseCode |
| `score_returned` | boolean | Whether a valid score was in the response |
| `consent_id` | UUID | Foreign key to consent_records |
| `request_timestamp` | timestamptz | UTC timestamp of request dispatch |
| `response_timestamp` | timestamptz | UTC timestamp of response receipt |
| `latency_ms` | integer | End-to-end API latency in milliseconds |
| `error_code` | string | FinSpark internal error code if applicable |

Audit log records are immutable. No application role has UPDATE or DELETE privilege on `bureau_audit_log`. Audit log is replicated to the SIEM (Splunk) within 60 seconds of write.

---

## 5. SLA Requirements

### 5.1 Response Time SLAs

| Endpoint | P50 | P95 | P99 | Hard Timeout |
|----------|-----|-----|-----|-------------|
| `POST /score/inquiry` | 1.2 s | 3.5 s | 6.0 s | 8 s |
| `POST /report/pull` (sync) | 2.5 s | 6.0 s | 10.0 s | 12 s |
| `POST /inquiry/bulk` (submission) | 0.5 s | 2.0 s | 4.0 s | 6 s |
| Bulk webhook delivery | — | — | — | 4 hours from submission |

Hard timeout behavior: On timeout, the integration service must return `ERR_BUREAU_TIMEOUT` to the LOS. The application must be queued for manual underwriting. The timeout event must be written to the audit log and to the ops alerting system.

### 5.2 Availability SLA

| Metric | Target | Measurement |
|--------|--------|-------------|
| Integration service uptime | 99.9% monthly | Excluding planned maintenance windows |
| CIBIL API availability (per CIBIL contract) | 99.5% monthly | CIBIL SLA reference: MSA-2024-FS-0089 |
| Score inquiry success rate | ≥ 98% of valid requests | Excluding NTC/NH consumers |
| Bulk job completion within SLA | ≥ 99.5% of submitted batches | Within 4-hour window |

### 5.3 Throughput Requirements

| Scenario | Peak Rate | Burst Rate |
|----------|-----------|-----------|
| Score inquiries (business hours) | 50 req/min | 200 req/min (30-second burst) |
| Report pulls | 20 req/min | 80 req/min (30-second burst) |
| Bulk submissions | 4 batches/hour | 8 batches/hour |

CIBIL has allocated a rate limit of 300 requests/minute for FinSpark's member account. The integration service must implement a token bucket rate limiter respecting this limit. Rate limit headers from CIBIL (`X-RateLimit-Remaining`, `X-RateLimit-Reset`) must be consumed and used to throttle.

### 5.4 Degraded Mode Operation

When CIBIL API availability drops below 95% within a 5-minute window, the integration service must automatically enter **Degraded Mode**:

1. Route all new score inquiries to the internal behavioral score model (if available for the applicant).
2. Log a `BUREAU_DEGRADED_MODE` event to the ops alerting topic.
3. Alert the on-call integration engineer via PagerDuty.
4. Queue all report pull requests for retry when service recovers.
5. Continue bulk submission with automatic retry logic.

---

## 6. Error Handling Requirements

### 6.1 CIBIL BureauResponseCode Mapping

| CIBIL BureauResponseCode | Meaning | FinSpark Action |
|--------------------------|---------|-----------------|
| `1` | Success | Process normally |
| `2` | No records found (NH) | Set hit_type = `NH`; apply NH policy |
| `3` | Insufficient data (NTC) | Set hit_type = `NTC`; apply NTC policy |
| `4` | Multiple matches found | Route to manual dedup workflow |
| `5` | Member account suspended | Alert CISO + ops immediately; halt all bureau calls |
| `6` | Invalid input data | Parse `ErrorDetails` array; return field-level validation errors to LOS |
| `7` | Duplicate request detected | Return cached response if within idempotency window; else treat as `1` |
| `8` | Consumer credit freeze active | Reject application with code `ADV_001`; do not retry |
| `51` | Rate limit exceeded | Implement exponential backoff: wait 60s, 120s, 240s before retry |
| `52` | Service temporarily unavailable | Retry with exponential backoff (see Section 6.3); enter degraded mode if persists |
| `99` | Unknown error | Log full response; alert ops; route to manual underwriting |

### 6.2 HTTP Status Code Handling

| HTTP Status | Handling |
|-------------|----------|
| 200 OK | Parse BureauResponseCode (above) |
| 202 Accepted | Async flow initiated (report pull / bulk submission) |
| 400 Bad Request | Log request (redact PII); parse error body; return `ERR_BUREAU_BAD_REQUEST`; do not retry |
| 401 Unauthorized | Invalidate cached credentials; re-fetch from Vault; retry once |
| 403 Forbidden | Check certificate validity; alert CISO if certificate not expired; do not retry |
| 404 Not Found | Log endpoint mismatch; alert integration team; do not retry |
| 429 Too Many Requests | Respect `Retry-After` header; apply token bucket backpressure |
| 500 Internal Server Error | Retry up to 3 times with exponential backoff; then route to manual |
| 503 Service Unavailable | Enter degraded mode (Section 5.4); queue for retry |

### 6.3 Retry Policy

| Scenario | Max Retries | Backoff | Jitter |
|----------|-------------|---------|--------|
| Network timeout | 3 | Exponential: 1s, 2s, 4s | ±500ms |
| HTTP 500 | 3 | Exponential: 5s, 10s, 20s | ±1s |
| HTTP 503 | 5 | Exponential: 10s, 20s, 40s, 80s, 160s | ±2s |
| HTTP 429 | Respect `Retry-After` | Fixed per header | None |
| Auth failure (401) | 1 | Immediate re-auth | None |

Retry attempts must be logged with attempt number, delay, and outcome. Exhausted retries must trigger a manual review alert.

### 6.4 FinSpark Internal Error Codes

| Error Code | Trigger Condition | LOS Behavior |
|------------|------------------|--------------|
| `ERR_BUREAU_PAN_INVALID` | PAN fails local regex validation | Block submission; surface to applicant |
| `ERR_BUREAU_CONSENT_MISSING` | No valid consent record found | Block; redirect to consent capture flow |
| `ERR_BUREAU_TIMEOUT` | Hard timeout exceeded | Queue for manual underwriting |
| `ERR_BUREAU_REPORT_FAILED` | Async report retrieval failed | Route to manual; alert underwriter |
| `ERR_BUREAU_NH` | No-hit response from bureau | Apply NH credit policy |
| `ERR_BUREAU_NTC` | Insufficient history | Apply NTC credit policy |
| `ERR_BUREAU_FROZEN` | Credit freeze on consumer | Adverse action; do not retry |
| `ERR_BUREAU_SUSPENDED` | Member account suspended | Halt all bureau calls; CISO escalation |
| `ERR_BUREAU_BAD_REQUEST` | HTTP 400 from CIBIL | Log and investigate; do not retry |
| `ERR_BUREAU_DEGRADED` | Degraded mode active | Use fallback scoring; notify ops |

---

## 7. Testing Requirements

### 7.1 Unit Testing

- All field mapping functions must have unit tests covering: valid inputs, boundary values, null/empty fields, invalid PAN, special characters in names.
- Score interpretation logic (Section 2.4.1) must have tests for all 6 score value categories.
- Reason code mapping must be tested for all codes in `cibil_reason_code_map.json`.
- Name splitting logic must be tested for: single-name applicants, hyphenated names, names with initials, names with titles (Mr./Ms./Dr.).

### 7.2 Integration Testing

- Integration tests must run against CIBIL's UAT environment (`https://api-uat.cibil.com/creditvision/v2`) using CIBIL-provided test PAN numbers.
- CIBIL UAT test PANs:

| Test PAN | Expected Score | Scenario |
|----------|---------------|----------|
| `TESTPAN001A` | 750 | High credit quality |
| `TESTPAN002B` | 580 | Below cutoff |
| `TESTPAN003C` | -1 | NTC (insufficient history) |
| `TESTPAN004D` | -2 | NH (no records) |
| `TESTPAN005E` | 999 | Credit freeze |
| `TESTPAN006F` | BRC=6 | Invalid data error |

- Integration tests must cover all three endpoints.
- Retry logic must be tested using the CIBIL chaos endpoint `POST /test/simulate-error?code=52`.

### 7.3 Security Testing

- Penetration test must be conducted on the integration service before go-live (scope: mTLS verification, API key handling, audit log integrity).
- DAST scan must verify PAN is never present in HTTP logs or error responses.
- Certificate pinning bypass test: verify that requests with a forged/unknown server certificate are rejected.
- Vault access test: verify that API keys are not accessible outside the integration service's Vault policy.

### 7.4 Performance Testing

- Load test: 300 concurrent score inquiries for 10 minutes. Pass criteria: P95 < 3.5s, error rate < 0.5%.
- Bulk submission test: Submit 3 batches × 5,000 records. Pass criteria: all webhook callbacks received within 4-hour window.
- Timeout test: Simulate CIBIL latency > 8s using the test environment. Verify ERR_BUREAU_TIMEOUT is returned within 8.5 seconds.

### 7.5 UAT Sign-off Criteria

| Test Area | Pass Criteria | Sign-off Owner |
|-----------|--------------|----------------|
| Score inquiry — happy path | Score returned, audit log written, LOS updated | Risk Analytics |
| Score inquiry — NTC/NH | Correct hit_type, policy applied | Risk Analytics |
| Full report — sync | Report stored, bureau_report_id returned to LOS | Integration Architect |
| Full report — async | Report delivered within 12 minutes | Integration Architect |
| Bulk inquiry | All results delivered, EWS triggered | Collections Risk |
| Security — mTLS | Rejected without valid client cert | CISO |
| Security — consent check | Rejected without valid consent record | Compliance |
| Audit log | All 19 fields populated, no PAN in plain text | Compliance + CISO |
| Degraded mode | Fallback activated within 30 seconds of CIBIL outage | Integration Architect |

---

## Appendix A — CIBIL EnquiryPurpose Code Mapping

| FinSpark Loan Type | CIBIL EnquiryPurpose Code |
|--------------------|--------------------------|
| `PERSONAL_LOAN` | `05` |
| `HOME_LOAN` | `01` |
| `AUTO_LOAN` | `04` |
| `CREDIT_CARD` | `10` |
| `MSME_TERM_LOAN` | `06` |
| `MSME_WORKING_CAPITAL` | `07` |
| `LOAN_AGAINST_PROPERTY` | `02` |
| `EDUCATION_LOAN` | `08` |
| `TWO_WHEELER_LOAN` | `09` |

## Appendix B — CIBIL Reason Code Mapping (Partial)

| CIBIL Code | Description | Adverse Action Letter Code |
|-----------|-------------|---------------------------|
| `R001` | Length of credit history is short | `AA-07` |
| `R002` | Too many recent enquiries | `AA-08` |
| `R003` | High credit utilization on revolving accounts | `AA-09` |
| `R004` | Presence of delinquency / DPD in recent 24 months | `AA-01` |
| `R005` | No active credit accounts in last 12 months | `AA-10` |
| `R006` | Derogatory public record present | `AA-02` |
| `R007` | High number of unsecured loan accounts | `AA-11` |
| `R008` | Missing or thin file — insufficient tradelines | `AA-12` |
