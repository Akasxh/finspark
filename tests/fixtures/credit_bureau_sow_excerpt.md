# Statement of Work — Excerpt
## CIBIL TransUnion Credit Bureau Integration
### FinSpark Lending Technology Pvt Ltd × CIBIL TransUnion CIBIL Ltd

**SOW Reference:** SOW-FS-CIBIL-2024-0089
**Master Services Agreement:** MSA-2024-FS-0089 (dated 2024-08-01)
**SOW Effective Date:** 2024-12-01
**SOW Expiry Date:** 2027-11-30 (3-year initial term; auto-renews annually)
**Governing Law:** Laws of India; jurisdiction Mumbai, Maharashtra
**Dispute Resolution:** Arbitration under ICADR Rules, seat Mumbai

---

## Section 1 — Parties and Engagement Summary

**Service Provider:** CIBIL TransUnion CIBIL Ltd, registered at One Indiabulls Centre, Tower 2A, 19th Floor, Elphinstone Road, Mumbai – 400 013. CIN: U72900MH2000PLC128297.

**Customer:** FinSpark Lending Technology Pvt Ltd, registered at 4th Floor, Prestige Tech Vista, Marathahalli-Sarjapur Outer Ring Road, Bengaluru – 560 103. CIN: U65999KA2021PTC145621.

FinSpark is a Reserve Bank of India (RBI) registered Non-Banking Financial Company (NBFC) holding certificate of registration number N-02.00462, licensed to operate a Lending Service Provider (LSP) platform under the RBI Master Direction — Digital Lending, 2022 (updated 2023).

This Statement of Work governs FinSpark's access to CIBIL's CreditVision® API Suite v2.1 for the purpose of automated credit bureau inquiry within FinSpark's loan origination, portfolio monitoring, and collections risk management workflows.

---

## Section 2 — Services to be Delivered

### 2.1 API Access Entitlements

CIBIL shall provision FinSpark with access to the following API products under this SOW:

| API Product | Product Code | Entitlement |
|-------------|-------------|-------------|
| CreditVision Score — Individual | CV-SCR-INDV | Unlimited (subject to rate limits; see Section 4) |
| CreditVision Full Report — Individual | CV-CIR-INDV | Unlimited (subject to rate limits) |
| Bulk Portfolio Inquiry | CV-BULK-PORT | Up to 1,50,000 records/month in Year 1; 3,00,000/month from Year 2 |
| UAT Environment Access | CV-UAT | Duration of SOW; 10,000 test calls/month |

Access is provisioned per FinSpark's Member Account ID: **MBR-FS-2024-00891**.

### 2.2 Onboarding Deliverables (CIBIL Obligations)

CIBIL shall deliver the following within 15 business days of SOW execution:

| Deliverable | Description | Delivery Timeline |
|-------------|-------------|-------------------|
| Member API Credentials | API key, HMAC signing secret | T+5 business days |
| Client Certificate Issuance | X.509 certificate signed by CIBIL-Member-CA-2024 | T+10 business days |
| UAT Environment Credentials | Separate API key and certificate for UAT | T+5 business days |
| UAT Test PAN Compendium | 50 test PAN scenarios covering all score ranges, error codes, and edge cases | T+10 business days |
| Integration Technical Guide | CreditVision API v2.1 Integration Guide (current version) | T+3 business days |
| Dedicated Integration Support | Named CIBIL integration engineer assigned for 90 days post-go-live | T+0 (from go-live date) |

### 2.3 Onboarding Deliverables (FinSpark Obligations)

FinSpark shall deliver the following before API production access is activated:

| Deliverable | Description | Due Date |
|-------------|-------------|----------|
| RBI Membership Confirmation | Copy of current Certificate of Registration | T+2 business days from SOW execution |
| Data Privacy Policy | Current privacy policy URL confirming DPDP Act 2023 compliance | T+5 business days |
| IT Security Questionnaire | Completed CIBIL security assessment form (CIBIL-SEC-FORM-2024) | T+10 business days |
| Penetration Test Certificate | Most recent VAPT certificate (not older than 12 months) | T+10 business days |
| Production IP Allowlist | Static egress IP addresses for API access allowlisting | T+3 business days |
| Webhook Endpoint Registration | Production callback URL for bulk inquiry results | T+3 business days |
| Go-Live Readiness Certification | Signed sign-off from FinSpark CISO confirming security controls | T+15 business days |

---

## Section 3 — Pricing and Volume Commitments

### 3.1 Fee Schedule

All fees are exclusive of applicable GST (currently 18%). GST to be charged at prevailing rate and billed as a separate line item.

| Service | Unit | Year 1 Rate | Year 2 Rate | Year 3 Rate |
|---------|------|-------------|-------------|-------------|
| CreditVision Score Inquiry | Per inquiry | INR 12.00 | INR 11.50 | INR 11.00 |
| CreditVision Full Report Pull | Per report | INR 38.00 | INR 36.00 | INR 34.00 |
| Bulk Portfolio Inquiry | Per record | INR 8.50 | INR 8.00 | INR 7.50 |
| Annual Membership Fee | Per year | INR 1,50,000 | INR 1,50,000 | INR 1,50,000 |
| Dedicated Integration Support (Year 1 only) | Flat | INR 2,00,000 | — | — |

### 3.2 Minimum Commitment

FinSpark commits to a minimum annual spend of INR 25,00,000 (INR 25 lakhs) excluding GST and the annual membership fee, across all API products combined.

If FinSpark's actual annual consumption falls below the minimum commitment, FinSpark shall pay the shortfall to CIBIL within 30 days of the annual invoice.

### 3.3 Volume Discount Thresholds

| Annual Score Inquiries | Discount on Inquiry Rate |
|----------------------|--------------------------|
| < 1,00,000 | Standard rate |
| 1,00,000 – 4,99,999 | 5% |
| 5,00,000 – 9,99,999 | 10% |
| ≥ 10,00,000 | 15% (requires written amendment) |

### 3.4 Billing Cycle and Payment Terms

- Billing cycle: Calendar month
- Invoice date: 5th of the following month
- Payment due: 30 days from invoice date (Net-30)
- Late payment: 1.5% per month on overdue amounts
- Payment method: NEFT/RTGS to CIBIL's designated bank account (details in MSA)
- Disputed invoices: Written notice within 15 days of invoice date; undisputed amount due on time

---

## Section 4 — Service Level Agreement

### 4.1 API Availability

| Service | Monthly Uptime SLA | Measurement Window | Exclusions |
|---------|-------------------|-------------------|------------|
| CreditVision Score API | 99.5% | Calendar month | Scheduled maintenance, Force Majeure |
| CreditVision Report API | 99.5% | Calendar month | Scheduled maintenance, Force Majeure |
| Bulk Inquiry Processing | 99.0% | Calendar month | Scheduled maintenance |

Uptime is measured from CIBIL's infrastructure monitoring. FinSpark shall independently monitor availability and may raise disputes within 5 business days of month-end with supporting evidence.

Scheduled maintenance windows: Sundays 02:00–06:00 IST. CIBIL shall provide at least 72 hours advance notice for any maintenance activity. Emergency maintenance: minimum 4-hour notice.

### 4.2 Response Time SLA (API Latency)

| Endpoint | P50 Commitment | P95 Commitment | Measurement |
|----------|---------------|---------------|-------------|
| POST /score/inquiry | ≤ 1.5 seconds | ≤ 4.0 seconds | Measured at CIBIL's API gateway |
| POST /report/pull | ≤ 3.0 seconds | ≤ 7.0 seconds | Measured at CIBIL's API gateway |
| POST /inquiry/bulk (submission) | ≤ 1.0 seconds | ≤ 3.0 seconds | Measured at CIBIL's API gateway |
| Bulk results webhook delivery | — | ≤ 4 hours from submission | End-to-end |

Note: CIBIL's SLA is measured at the CIBIL API gateway. Network transit time between FinSpark and CIBIL is excluded from CIBIL's SLA but included in FinSpark's internal SLA (see BRD-INT-2024-047 Section 5.1).

### 4.3 Rate Limits

| Endpoint | Rate Limit | Burst Allowance |
|----------|-----------|----------------|
| POST /score/inquiry | 300 requests/minute | 600 for 30 seconds (once/hour) |
| POST /report/pull | 150 requests/minute | 300 for 30 seconds (once/hour) |
| POST /inquiry/bulk | 10 submissions/hour | None |

Rate limits apply per member account. FinSpark may request rate limit increase with 30-day written notice; CIBIL shall respond within 15 business days.

### 4.4 SLA Credits

In the event CIBIL fails to meet availability SLAs, FinSpark is entitled to service credits as follows:

| Monthly Uptime Achieved | Credit as % of Monthly Invoice |
|------------------------|-------------------------------|
| 99.0% – 99.4% | 5% |
| 95.0% – 98.9% | 10% |
| 90.0% – 94.9% | 20% |
| < 90.0% | 30% (and FinSpark may terminate without penalty) |

SLA credits are the sole and exclusive remedy for availability failures. Credits must be claimed within 30 days of the affected month-end.

### 4.5 Incident Response SLA

| Incident Severity | Definition | CIBIL Response Time | Resolution Target |
|-------------------|-----------|--------------------|--------------------|
| P1 — Critical | API completely unavailable; all requests failing | 30 minutes | 4 hours |
| P2 — High | > 50% error rate; latency > 3× P95 SLA | 2 hours | 8 hours |
| P3 — Medium | Degraded performance; isolated errors | 4 hours | 24 hours |
| P4 — Low | Non-production issues; documentation queries | 1 business day | 5 business days |

CIBIL shall maintain a 24×7 P1/P2 incident hotline. FinSpark's designated escalation contact for P1 incidents is the Integration Architect (Rajesh Nair) and CISO (Deepa Krishnan).

---

## Section 5 — Data Handling and Compliance

### 5.1 Data Ownership and Licensing

All credit information delivered under this SOW remains the property of CIBIL and the reporting member institutions. FinSpark is granted a limited, non-exclusive, non-transferable license to use credit information solely for:
- Credit assessment of individual applicants who have provided consent
- Portfolio monitoring of existing FinSpark loan accounts
- Collections risk assessment for FinSpark's own loan portfolio

**Prohibited uses:**
- Resale or sublicensing of bureau data to third parties
- Marketing or solicitation purposes
- Benchmarking or competitive analysis
- Training or fine-tuning of machine learning models on raw bureau data without explicit written consent from CIBIL

### 5.2 Regulatory Compliance Obligations

Both parties acknowledge that this integration is subject to:

1. **Credit Information Companies (Regulation) Act, 2005 (CICRA)** — FinSpark's access is predicated on its membership in CIBIL as a credit institution. FinSpark shall maintain its membership in good standing.

2. **RBI Master Direction — Credit Information Reporting, 2023** — FinSpark shall submit accurate and timely credit data updates per CIBIL's reporting guidelines.

3. **RBI Master Direction — Digital Lending, 2022 (as amended)** — Bureau pulls must be associated with a verifiable, timestamped customer consent record meeting RBI's consent architecture requirements.

4. **Digital Personal Data Protection Act, 2023 (DPDP Act)** — Consumer PAN, date of birth, mobile number, and bureau report data constitute "personal data" and "sensitive personal data" under the Act. FinSpark agrees to:
   - Collect and use such data only for the declared purpose
   - Retain data only for the periods specified in this SOW and applicable regulation
   - Delete data upon expiry of retention period or upon consumer deletion request (where legally permissible)
   - Notify CIBIL within 72 hours of any data breach involving CIBIL-sourced data

5. **CIBIL Code of Conduct for Credit Institutions** — FinSpark shall not use adverse credit information to discriminate on grounds prohibited under the Indian Constitution.

### 5.3 Data Retention and Deletion

| Data Type | Retention Period | Basis |
|-----------|-----------------|-------|
| Individual credit scores | 7 years from inquiry date | RBI Master Direction |
| Full CIR reports | 7 years from report date | RBI Master Direction |
| Adverse action reason codes | Life of loan + 2 years | Regulatory best practice |
| Consent records | 5 years from last use | DPDP Act guidance |
| API audit logs | 7 years | IT Act requirements |

### 5.4 Security Requirements

FinSpark shall maintain the following security controls for the duration of this SOW:

- All API communication over TLS 1.3 (TLS 1.2 permitted only as legacy fallback with CISO approval)
- API keys stored in a Hardware Security Module (HSM) or approved secrets management solution (HashiCorp Vault with FIPS 140-2 Level 2 backend qualifies)
- No API keys or cryptographic material in source code, CI/CD pipelines, or container images
- mTLS client certificates stored in a certificate management system; private keys never persisted to disk in plaintext
- Annual penetration tests covering the integration layer; reports shared with CIBIL on request
- IP allowlisting: Only FinSpark's pre-registered static egress IPs may access CIBIL APIs
- Access logging: All API calls must be logged with timestamp, calling user/service, and outcome

CIBIL reserves the right to audit FinSpark's compliance with these security requirements on 30-day written notice.

---

## Section 6 — Intellectual Property

### 6.1 CIBIL IP

The CreditVision API, credit bureau data, scoring algorithms, and API documentation are and remain CIBIL's exclusive intellectual property. FinSpark obtains no ownership right in any CIBIL IP under this SOW.

### 6.2 FinSpark IP

Integration code, field mapping configurations, transformation logic, and FinSpark's internal risk models developed using (but not containing) bureau data remain FinSpark's exclusive property.

### 6.3 Derived Data

Credit scores, extracted structured fields, and derived features computed from bureau data are subject to the usage restrictions in Section 5.1.

---

## Section 7 — Term, Termination, and Transition

### 7.1 Term

Initial term: 3 years from SOW Effective Date (2024-12-01 to 2027-11-30). Auto-renews for successive 1-year terms unless either party provides 90-day written notice before term expiry.

### 7.2 Termination for Convenience

Either party may terminate this SOW without cause with 180 days written notice. FinSpark remains liable for minimum commitments (Section 3.2) through the notice period.

### 7.3 Termination for Cause

Either party may terminate immediately upon:
- Material breach not cured within 30 days of written notice
- Insolvency or liquidation of either party
- Loss of RBI registration by FinSpark
- CIBIL deregistering FinSpark as a credit institution member
- Repeated SLA failures entitling FinSpark to termination credits (Section 4.4)

### 7.4 Post-Termination Data Obligations

Upon termination, FinSpark shall:
1. Immediately cease all new bureau API calls
2. Revoke all CIBIL-issued API credentials and certificates
3. Retain existing bureau data in accordance with retention schedules (Section 5.3)
4. Provide CIBIL with a written data deletion certificate within 90 days of retention expiry

---

## Section 8 — Limitation of Liability

**8.1** CIBIL's aggregate liability under this SOW for any 12-month period shall not exceed the total fees paid by FinSpark to CIBIL in that 12-month period.

**8.2** Neither party shall be liable for indirect, consequential, punitive, or exemplary damages, loss of profits, or loss of business opportunity.

**8.3** Notwithstanding 8.1 and 8.2, liability caps shall not apply to: (a) death or personal injury, (b) fraud or willful misconduct, (c) breach of data protection obligations under DPDP Act 2023.

---

## Section 9 — Change Management

### 9.1 API Versioning Policy

CIBIL commits to:
- Minimum 12 months' notice before deprecating any API version
- Maintaining at least 2 supported API versions concurrently
- Publishing a migration guide at least 90 days before a version is deprecated
- Providing a migration support window with dedicated engineering support

CIBIL's current API deprecation schedule: v1 (XML) end-of-life 2025-12-31. All members on v1 must migrate to v2 by this date.

### 9.2 Breaking vs Non-Breaking Changes

CIBIL shall distinguish between breaking and non-breaking changes:

**Non-breaking (deployed with 30-day notice):** New optional request fields, new optional response fields, new enum values for non-critical fields, bug fixes, performance improvements.

**Breaking (deployed with 90-day notice and version increment):** Removal of fields, changes to required fields, changes to response structure, new required authentication layers, changes to rate limiting.

### 9.3 SOW Change Orders

Any change to the scope, pricing, or service levels in this SOW requires a written Change Order signed by authorized representatives of both parties. Change Orders become effective on the later of: (a) the date signed by both parties, or (b) the effective date stated in the Change Order.

---

## Signatories

| Role | Name | Designation | Signature | Date |
|------|------|-------------|-----------|------|
| FinSpark — Authorized Signatory | Karan Mehta | CEO, FinSpark Lending Technology Pvt Ltd | _______________ | 2024-11-28 |
| FinSpark — Technical Owner | Rajesh Nair | VP Engineering & Integration Architect | _______________ | 2024-11-28 |
| CIBIL — Authorized Signatory | Anand Krishnamurthy | MD & CEO, CIBIL TransUnion CIBIL Ltd | _______________ | 2024-11-29 |
| CIBIL — Account Manager | Vikram Joshi | Senior Relationship Manager — Enterprise | _______________ | 2024-11-29 |

---

*This document is an excerpt from SOW-FS-CIBIL-2024-0089. Sections 10 (Dispute Resolution), 11 (Indemnification), 12 (Representations and Warranties), and Schedules A–D are contained in the full executed SOW on file with both parties' legal departments.*
