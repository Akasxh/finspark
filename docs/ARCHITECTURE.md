# FinSpark Architecture Documentation

> AI-Assisted Integration Configuration & Orchestration Engine for Enterprise Lending Platforms

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Flow](#2-data-flow)
3. [Database Schema](#3-database-schema)
4. [Integration Lifecycle State Machine](#4-integration-lifecycle-state-machine)
5. [Module Interaction](#5-module-interaction)
6. [API Route Map](#6-api-route-map)
7. [Security Architecture](#7-security-architecture)

---

## 1. System Overview

FinSpark is a multi-tenant platform that automates the configuration and testing of third-party API integrations for Indian lending platforms. It parses BRD/SOW documents, matches them to pre-built adapters (CIBIL, eKYC, GST, Payment, Fraud, SMS), generates integration configurations with intelligent field mapping, and validates them through a simulation framework -- all without writing code.

### C4 Container Diagram

```mermaid
C4Context
    title FinSpark - System Container Diagram

    Person(user, "Platform Engineer", "Configures and manages integrations")
    Person(auditor, "Compliance Auditor", "Reviews audit trails and security")

    Enterprise_Boundary(ext, "External Systems") {
        System_Ext(brd_docs, "BRD/SOW Documents", "DOCX, PDF, YAML, JSON specs")
        System_Ext(cibil, "CIBIL Bureau API", "Credit score & report")
        System_Ext(ekyc, "Aadhaar eKYC API", "Identity verification")
        System_Ext(gst, "GST Verification API", "GSTIN validation")
        System_Ext(payment, "Payment Gateway API", "NEFT/IMPS/RTGS/UPI")
        System_Ext(fraud, "Fraud Detection API", "Risk scoring")
        System_Ext(sms, "SMS Gateway API", "Notification delivery")
    }

    Enterprise_Boundary(finspark, "FinSpark Platform") {

        Container_Boundary(frontend_boundary, "Presentation Layer") {
            Container(react_app, "React Dashboard", "React 18, TypeScript, Vite, TanStack Query, Recharts", "Real-time metrics, adapter catalog, config management UI")
        }

        Container_Boundary(api_boundary, "API Layer") {
            Container(fastapi, "FastAPI Application", "Python 3.12, FastAPI, Pydantic v2", "REST API with OpenAPI docs, SSE streaming, file uploads")
        }

        Container_Boundary(middleware_boundary, "Cross-Cutting Middleware") {
            Container(tenant_mw, "Tenant Middleware", "Starlette BaseHTTPMiddleware", "Extracts X-Tenant-ID/Name/Role headers, injects into request state")
            Container(rate_limiter, "Rate Limiter", "Sliding-window token bucket", "Per-tenant 100 req/60s with Retry-After headers")
            Container(req_logger, "Request Logger", "Structured logging", "Method, path, status, duration_ms, tenant_id per request")
        }

        Container_Boundary(modules, "Core Modules") {
            Container(parser, "Parsing Engine", "regex + docx/pdf/yaml/json parsers", "Extracts endpoints, fields, auth, services, SLA from documents")
            Container(registry, "Integration Registry", "SQLAlchemy async, selectinload", "Manages adapter catalog with versioned schemas and endpoints")
            Container(config_engine, "Config Engine", "rapidfuzz, synonym dictionaries", "Field mapping (fuzzy + semantic), config generation, diff analysis")
            Container(simulator, "Simulation Framework", "MockAPIServer + IntegrationSimulator", "7-step validation: structure, mappings, endpoints, auth, hooks, errors, retry")
            Container(lifecycle, "Lifecycle Manager", "Finite state machine", "Enforces draft->configured->validating->testing->active->deprecated transitions")
        }

        Container_Boundary(security_boundary, "Security Layer") {
            Container(credential_vault, "Credential Vault", "Fernet symmetric encryption (SHA-256 derived key)", "Encrypts API keys, webhook secrets, auth credentials at rest")
            Container(pii_masker, "PII Masker", "Regex pattern matching", "Masks Aadhaar, PAN, phone, email, account numbers in logs")
            Container(jwt_engine, "JWT Engine", "PyJWT, HS256", "Token creation and validation with configurable expiry")
            Container(audit_logger, "Audit Logger", "Immutable append-only log", "Tracks all mutations: create, update, delete, deploy, rollback")
        }

        Container_Boundary(data_boundary, "Data Layer") {
            ContainerDb(db, "Database", "SQLite (dev) / PostgreSQL (prod)", "11 tables with UUID PKs, tenant isolation, timestamp tracking")
        }
    }

    Rel(user, react_app, "Manages integrations", "HTTPS")
    Rel(auditor, react_app, "Reviews audit logs", "HTTPS")
    Rel(react_app, fastapi, "API calls", "HTTP/JSON, SSE")
    Rel(fastapi, tenant_mw, "Every request passes through")
    Rel(tenant_mw, rate_limiter, "After tenant extraction")
    Rel(rate_limiter, req_logger, "If not rate-limited")

    Rel(fastapi, parser, "POST /documents/upload")
    Rel(fastapi, registry, "GET/POST /adapters")
    Rel(fastapi, config_engine, "POST /configurations/generate")
    Rel(fastapi, simulator, "POST /simulations/run")
    Rel(fastapi, lifecycle, "POST /configurations/{id}/transition")
    Rel(fastapi, audit_logger, "All mutations")

    Rel(parser, brd_docs, "Reads & extracts")
    Rel(simulator, cibil, "Mock simulation")
    Rel(simulator, ekyc, "Mock simulation")
    Rel(simulator, gst, "Mock simulation")
    Rel(simulator, payment, "Mock simulation")
    Rel(simulator, fraud, "Mock simulation")
    Rel(simulator, sms, "Mock simulation")

    Rel(config_engine, db, "CRUD configs")
    Rel(registry, db, "CRUD adapters")
    Rel(audit_logger, db, "Append-only writes")
    Rel(credential_vault, db, "Encrypted storage")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```

### Component Summary

| Layer | Component | Technology | Responsibility |
|-------|-----------|------------|----------------|
| Frontend | React Dashboard | React 18, TypeScript, Vite, Recharts | Metrics visualization, adapter browsing, config management |
| API | FastAPI Application | FastAPI, Pydantic v2, Uvicorn | REST endpoints, OpenAPI docs, SSE streaming |
| Middleware | Tenant Middleware | Starlette | Multi-tenant context injection via X-Tenant-ID header |
| Middleware | Rate Limiter | In-memory sliding window | 100 requests/60s per tenant, 429 with Retry-After |
| Middleware | Request Logger | Python logging | Structured request/response metrics |
| Module | Parsing Engine | python-docx, pypdf, PyYAML | Document parsing and entity extraction |
| Module | Integration Registry | SQLAlchemy async | Adapter catalog with versioned schemas |
| Module | Config Engine | rapidfuzz | Fuzzy field mapping, config generation, diff engine |
| Module | Simulation Framework | MockAPIServer | 7-step mock integration testing |
| Module | Lifecycle Manager | FSM dataclass | State transition enforcement with audit trail |
| Security | Credential Vault | cryptography.Fernet | Symmetric encryption for secrets at rest |
| Security | PII Masker | Regex | Aadhaar, PAN, phone, email, account masking |
| Security | JWT Engine | PyJWT | HS256 token management |
| Security | Audit Logger | SQLAlchemy | Immutable audit trail for all mutations |
| Data | Database | SQLite/PostgreSQL | 11 tables, UUID PKs, async sessions |

---

## 2. Data Flow

### End-to-End Integration Configuration Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as Platform Engineer
    participant FE as React Dashboard
    participant API as FastAPI Gateway
    participant TM as Tenant Middleware
    participant RL as Rate Limiter
    participant PE as Parsing Engine
    participant AR as Adapter Registry
    participant CE as Config Engine
    participant FM as Field Mapper
    participant SF as Simulation Framework
    participant MS as Mock API Server
    participant LC as Lifecycle Manager
    participant AL as Audit Logger
    participant CV as Credential Vault
    participant DB as Database

    rect rgb(30, 41, 59)
        Note over U,DB: Phase 1 - Document Upload & Parsing
        U->>FE: Upload BRD/SOW document
        FE->>API: POST /api/v1/documents/upload<br/>(multipart/form-data)
        API->>TM: Extract tenant from X-Tenant-ID header
        TM->>RL: Check rate limit (100 req/60s)
        RL-->>API: Allowed
        API->>PE: parse(file_path, doc_type)
        PE->>PE: Detect format (docx/pdf/yaml/json)

        alt DOCX/PDF Document
            PE->>PE: Extract full text from paragraphs & tables
            PE->>PE: Regex extraction: endpoints, fields, auth, services
            PE->>PE: Extract sections, security reqs, SLA reqs
        else OpenAPI YAML/JSON
            PE->>PE: Parse paths -> endpoints
            PE->>PE: Parse components/schemas -> fields
            PE->>PE: Parse securitySchemes -> auth requirements
        end

        PE-->>API: ParsedDocumentResult {endpoints, fields, auth, services, confidence}
        API->>DB: INSERT document (status=parsed)
        API->>AL: log(upload_document, document, doc.id)
        AL->>DB: INSERT audit_log
        API-->>FE: DocumentUploadResponse {id, status, filename}
    end

    rect rgb(30, 50, 40)
        Note over U,DB: Phase 2 - Adapter Matching
        U->>FE: Browse adapter catalog
        FE->>API: GET /api/v1/adapters/?category=bureau
        API->>AR: list_adapters(category)
        AR->>DB: SELECT adapters JOIN adapter_versions
        DB-->>AR: Adapter[] with versions
        AR-->>API: Adapters with endpoints, schemas, auth types
        API-->>FE: AdapterListResponse {adapters, categories}
        U->>FE: Select adapter version (e.g., CIBIL v2)
    end

    rect rgb(50, 30, 40)
        Note over U,DB: Phase 3 - Configuration Generation
        U->>FE: Generate config (document + adapter version)
        FE->>API: POST /api/v1/configurations/generate<br/>{document_id, adapter_version_id, name}
        API->>DB: Fetch parsed document + adapter version
        API->>CE: generate(parsed_result, adapter_version)
        CE->>FM: map_fields(source_fields, target_fields)

        loop For each source field
            FM->>FM: Strategy 1: Exact synonym match<br/>(FIELD_SYNONYMS dictionary)
            FM->>FM: Strategy 2: Fuzzy match<br/>(rapidfuzz token_sort_ratio >= 60%)
            FM->>FM: Strategy 3: Partial token overlap<br/>(Jaccard similarity >= 0.6)
        end

        FM-->>CE: FieldMapping[] with confidence scores
        CE->>CE: Build endpoint configs
        CE->>CE: Generate transformation rules
        CE->>CE: Attach default hooks (audit_logger, pii_masker, schema_validator)
        CE->>CE: Set retry policy {max_retries: 3, backoff: 2}
        CE-->>API: Complete config JSON

        API->>DB: INSERT configuration (status=configured)
        API->>DB: INSERT configuration_history (version=1)
        API->>AL: log(generate_config, configuration, config.id)
        API-->>FE: ConfigurationResponse {id, field_mappings, status}
    end

    rect rgb(40, 30, 60)
        Note over U,DB: Phase 4 - Simulation & Testing
        U->>FE: Run simulation
        FE->>API: POST /api/v1/simulations/run<br/>{configuration_id, test_type: "full"}
        API->>DB: Fetch configuration
        API->>SF: run_simulation(full_config, "full")

        SF->>SF: Step 1: Validate config structure<br/>(required keys: adapter_name, version, base_url, auth, endpoints, field_mappings)
        SF->>SF: Step 2: Validate field mappings<br/>(coverage >= 70%, low confidence <= 30%)

        loop For each enabled endpoint
            SF->>MS: generate_response(endpoint, request_payload)
            MS->>MS: Generate mock data from Indian fintech domain<br/>(PAN, Aadhaar, GSTIN, IFSC, etc.)
            MS-->>SF: Mock API response
            SF->>SF: Step 3+: Validate endpoint response
        end

        SF->>SF: Step N-2: Validate auth configuration
        SF->>SF: Step N-1: Validate hooks (pre_request, post_response, on_error, on_timeout)
        SF->>SF: Step N: Test error handling (retry policy, timeout, error hooks)
        SF->>SF: Step N+1: Test retry logic (max_retries 1-5, backoff, status codes)

        SF-->>API: SimulationStepResult[] {step_name, status, duration_ms, confidence_score}
        API->>DB: INSERT simulation + simulation_steps
        API->>DB: UPDATE configuration.status = "testing" (if all passed)
        API->>AL: log(run_simulation, simulation, sim.id)
        API-->>FE: SimulationResponse {passed: N, failed: M, steps}
    end

    rect rgb(30, 45, 50)
        Note over U,DB: Phase 5 - Deploy (Lifecycle Transition)
        U->>FE: Promote to Active
        FE->>API: POST /api/v1/configurations/{id}/transition<br/>{target_state: "active"}
        API->>LC: transition(TESTING -> ACTIVE)
        LC->>LC: Validate transition allowed (FSM check)
        LC-->>API: AuditEntry {from_state, to_state, timestamp}
        API->>DB: UPDATE configuration.status = "active"
        API->>AL: log(deploy, configuration, config.id)
        API-->>FE: TransitionResponse {previous_state, new_state}
    end
```

### SSE Streaming Flow (Real-Time Simulation)

```mermaid
sequenceDiagram
    participant FE as React Dashboard
    participant API as FastAPI
    participant SF as Simulator

    FE->>API: GET /api/v1/simulations/{id}/stream
    API->>SF: run_simulation_stream(config)

    loop For each test step
        SF-->>API: SimulationStepResult
        API-->>FE: event: step\ndata: {step_name, status, duration_ms}
    end

    API-->>FE: event: done\ndata: {total_steps: N}
```

---

## 3. Database Schema

### Entity-Relationship Diagram

```mermaid
erDiagram
    tenants {
        string id PK "UUID v4"
        string name "NOT NULL, VARCHAR(255)"
        string slug "UNIQUE, VARCHAR(100)"
        text description "nullable"
        boolean is_active "DEFAULT true"
        text settings "JSON - tenant preferences"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    documents {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string filename "NOT NULL, VARCHAR(500)"
        string file_type "NOT NULL (docx|pdf|yaml|json)"
        integer file_size "DEFAULT 0"
        string doc_type "NOT NULL (brd|sow|api_spec|other)"
        string status "(uploaded|parsing|parsed|failed)"
        text raw_text "nullable, first 5000 chars"
        text parsed_result "JSON - ParsedDocumentResult"
        text error_message "nullable"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    adapters {
        string id PK "UUID v4"
        string name "NOT NULL, VARCHAR(255)"
        string category "NOT NULL (bureau|kyc|gst|payment|fraud|notification)"
        text description "nullable"
        boolean is_active "DEFAULT true"
        string icon "nullable, VARCHAR(50)"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    adapter_versions {
        string id PK "UUID v4"
        string adapter_id FK "NOT NULL -> adapters.id"
        string version "NOT NULL, VARCHAR(20)"
        integer version_order "DEFAULT 0"
        string status "(active|deprecated|beta)"
        string base_url "nullable, VARCHAR(500)"
        string auth_type "(api_key|oauth2|certificate|api_key_certificate)"
        text request_schema "JSON Schema"
        text response_schema "JSON Schema"
        text endpoints "JSON array of endpoint objects"
        text config_template "JSON default config"
        text changelog "nullable"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    configurations {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string name "NOT NULL, VARCHAR(255)"
        string adapter_version_id FK "NOT NULL -> adapter_versions.id"
        string document_id FK "nullable -> documents.id"
        string status "(draft|configured|validating|testing|active|deprecated|rollback)"
        integer version "DEFAULT 1"
        text field_mappings "JSON array of FieldMapping"
        text transformation_rules "JSON array of TransformationRule"
        text hooks "JSON array of HookConfig"
        text auth_config "JSON, Fernet encrypted"
        text full_config "JSON - complete configuration"
        text notes "nullable"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    configuration_history {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string configuration_id FK "NOT NULL -> configurations.id"
        integer version "NOT NULL"
        string change_type "(created|updated|status_change)"
        text previous_value "JSON nullable"
        text new_value "JSON nullable"
        string changed_by "nullable, VARCHAR(255)"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    simulations {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string configuration_id FK "NOT NULL -> configurations.id"
        string status "(pending|running|passed|failed|error)"
        string test_type "(full|smoke|schema_only|parallel_version)"
        integer total_tests "DEFAULT 0"
        integer passed_tests "DEFAULT 0"
        integer failed_tests "DEFAULT 0"
        integer duration_ms "nullable"
        text results "JSON array of SimulationStepResult"
        text error_log "nullable"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    simulation_steps {
        string id PK "UUID v4"
        string simulation_id FK "NOT NULL -> simulations.id"
        string step_name "NOT NULL, VARCHAR(255)"
        integer step_order "DEFAULT 0"
        string status "(pending|passed|failed|skipped|error)"
        text request_payload "JSON"
        text expected_response "JSON"
        text actual_response "JSON"
        integer duration_ms "nullable"
        float confidence_score "nullable, 0.0-1.0"
        text error_message "nullable"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    audit_logs {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string actor "NOT NULL, VARCHAR(255)"
        string action "NOT NULL (create|update|delete|deploy|rollback)"
        string resource_type "NOT NULL (configuration|adapter|simulation|document)"
        string resource_id "NOT NULL, VARCHAR(36)"
        text details "JSON nullable"
        string ip_address "nullable, VARCHAR(45)"
        string user_agent "nullable, VARCHAR(500)"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    webhooks {
        string id PK "UUID v4"
        string tenant_id FK "INDEX, NOT NULL"
        string url "NOT NULL, VARCHAR(2048)"
        string secret "NOT NULL, Fernet encrypted"
        text events "JSON list of event types"
        boolean is_active "DEFAULT true"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    webhook_deliveries {
        string id PK "UUID v4"
        string webhook_id FK "NOT NULL -> webhooks.id, ON DELETE CASCADE"
        string event_type "NOT NULL, VARCHAR(100)"
        text payload "JSON, NOT NULL"
        string status "(pending|delivered|failed)"
        integer response_code "nullable"
        integer attempts "DEFAULT 0"
        datetime created_at "server_default now()"
        datetime updated_at "onupdate now()"
    }

    adapters ||--o{ adapter_versions : "has versions"
    configurations }o--|| adapter_versions : "uses"
    configurations }o--o| documents : "generated from"
    configurations ||--o{ configuration_history : "has history"
    configurations ||--o{ simulations : "tested by"
    simulations ||--o{ simulation_steps : "contains steps"
    webhooks ||--o{ webhook_deliveries : "delivers to"
```

### Table Count: 11 Tables

| Table | Row-Level Tenant Isolation | Purpose |
|-------|:-:|---------|
| `tenants` | -- | Tenant registry and settings |
| `documents` | Yes | Uploaded BRD/SOW/API spec files |
| `adapters` | -- | Pre-built adapter catalog (global) |
| `adapter_versions` | -- | Versioned adapter schemas (global) |
| `configurations` | Yes | Generated integration configs per tenant |
| `configuration_history` | Yes | Version history of config changes |
| `simulations` | Yes | Simulation/test run records |
| `simulation_steps` | -- | Individual test steps within simulations |
| `audit_logs` | Yes | Immutable audit trail |
| `webhooks` | Yes | Registered webhook endpoints |
| `webhook_deliveries` | -- | Webhook delivery attempt records |

---

## 4. Integration Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> draft : Configuration created

    draft --> configured : Config generated from<br/>document + adapter
    configured --> draft : Reset to draft<br/>(re-edit)
    configured --> validating : Start validation<br/>(POST /validate)
    validating --> configured : Validation failed<br/>(errors found)
    validating --> testing : Validation passed<br/>(POST /simulations/run)
    testing --> configured : Tests failed<br/>(re-configure)
    testing --> active : All tests passed<br/>(promote to production)
    active --> deprecated : End of life<br/>(sunset integration)
    active --> rollback : Emergency rollback<br/>(production issue)
    deprecated --> draft : Revive integration<br/>(create new version)
    rollback --> configured : Fix and re-configure
    rollback --> draft : Full reset

    state draft {
        [*] --> editing
        editing --> editing : Modify mappings/hooks
    }

    state configured {
        [*] --> field_mappings_set
        field_mappings_set --> hooks_configured
        hooks_configured --> auth_configured
    }

    state testing {
        [*] --> structure_test
        structure_test --> mapping_test
        mapping_test --> endpoint_tests
        endpoint_tests --> auth_test
        auth_test --> hook_test
        hook_test --> error_test
        error_test --> retry_test
        retry_test --> [*]
    }

    note right of draft
        Entry point for all
        new configurations
    end note

    note right of active
        Production-ready
        Full audit trail
    end note

    note left of rollback
        Emergency state
        Requires manual
        re-configuration
    end note
```

### Transition Rules

| From State | Allowed Targets | Trigger |
|-----------|----------------|---------|
| `draft` | `configured` | Config generation from document + adapter |
| `configured` | `validating`, `draft` | Start validation or reset |
| `validating` | `testing`, `configured` | Pass/fail validation |
| `testing` | `active`, `configured` | Pass/fail simulation |
| `active` | `deprecated`, `rollback` | Sunset or emergency |
| `deprecated` | `draft` | Revive as new version |
| `rollback` | `configured`, `draft` | Fix or full reset |

---

## 5. Module Interaction Diagram

```mermaid
flowchart TB
    subgraph External["External Inputs"]
        DOC["BRD / SOW / OpenAPI<br/>(DOCX, PDF, YAML, JSON)"]
        PROVIDER["Provider APIs<br/>(CIBIL, eKYC, GST, Payment, Fraud, SMS)"]
    end

    subgraph API["FastAPI API Layer"]
        direction LR
        DOC_ROUTE["/documents"]
        ADAPT_ROUTE["/adapters"]
        CONFIG_ROUTE["/configurations"]
        SIM_ROUTE["/simulations"]
        AUDIT_ROUTE["/audit"]
        WEBHOOK_ROUTE["/webhooks"]
        HEALTH_ROUTE["/health"]
        METRICS_ROUTE["/metrics"]
    end

    subgraph Middleware["Middleware Stack (execution order)"]
        direction LR
        CORS["CORS<br/>(allow all origins)"]
        TENANT["Tenant Middleware<br/>(X-Tenant-ID extraction)"]
        RATE["Rate Limiter<br/>(100 req/60s per tenant)"]
        LOG["Request Logger<br/>(duration, status, path)"]
    end

    subgraph Services["Core Services"]
        PARSER["DocumentParser<br/>- parse_docx()<br/>- parse_pdf()<br/>- parse_openapi()<br/>- extract_fields()<br/>- extract_endpoints()<br/>- extract_auth()"]

        REGISTRY["AdapterRegistry<br/>- list_adapters()<br/>- get_adapter()<br/>- create_adapter()<br/>- add_version()<br/>- find_matching()"]

        CONFIG_GEN["ConfigGenerator<br/>- generate()<br/>- build_endpoints()<br/>- generate_hooks()"]

        FIELD_MAP["FieldMapper<br/>- map_fields()<br/>- synonym_match()<br/>- fuzzy_match()<br/>- token_overlap()"]

        DIFF_ENGINE["ConfigDiffEngine<br/>- compare()<br/>- detect_breaking()"]

        SIMULATOR["IntegrationSimulator<br/>- run_simulation()<br/>- run_stream()<br/>- parallel_version_test()"]

        MOCK_SERVER["MockAPIServer<br/>- generate_response()<br/>- Indian fintech mock data"]

        LIFECYCLE["IntegrationLifecycle<br/>- can_transition()<br/>- transition()<br/>- get_available()"]
    end

    subgraph Security["Security Services"]
        VAULT["Credential Vault<br/>(Fernet AES-128-CBC)"]
        PII["PII Masker<br/>(Aadhaar, PAN, phone,<br/>email, account)"]
        JWT["JWT Engine<br/>(HS256, configurable expiry)"]
        AUDIT_SVC["AuditService<br/>(immutable append-only)"]
    end

    subgraph Data["Data Layer"]
        DB[(SQLite / PostgreSQL)]
        UPLOADS[("/uploads/{tenant_id}/")]
    end

    DOC --> DOC_ROUTE
    PROVIDER -.->|"Mock in simulation"| MOCK_SERVER

    CORS --> TENANT --> RATE --> LOG --> API

    DOC_ROUTE --> PARSER
    ADAPT_ROUTE --> REGISTRY
    CONFIG_ROUTE --> CONFIG_GEN
    CONFIG_ROUTE --> DIFF_ENGINE
    SIM_ROUTE --> SIMULATOR
    AUDIT_ROUTE --> AUDIT_SVC
    WEBHOOK_ROUTE --> VAULT

    CONFIG_GEN --> FIELD_MAP
    SIMULATOR --> MOCK_SERVER
    CONFIG_GEN --> LIFECYCLE

    PARSER -->|"Parsed fields"| CONFIG_GEN
    REGISTRY -->|"Adapter schemas"| CONFIG_GEN
    REGISTRY -->|"Adapter schemas"| SIMULATOR

    VAULT --> DB
    PII --> LOG
    AUDIT_SVC --> DB
    REGISTRY --> DB
    CONFIG_GEN --> DB
    SIMULATOR --> DB
    PARSER --> UPLOADS

    classDef external fill:#1e3a5f,stroke:#3b82f6,color:#fff
    classDef api fill:#1e3a2f,stroke:#10b981,color:#fff
    classDef middleware fill:#3a1e3f,stroke:#a855f7,color:#fff
    classDef service fill:#3a2e1e,stroke:#f59e0b,color:#fff
    classDef security fill:#3a1e1e,stroke:#ef4444,color:#fff
    classDef data fill:#1e2a3a,stroke:#6b7280,color:#fff

    class DOC,PROVIDER external
    class DOC_ROUTE,ADAPT_ROUTE,CONFIG_ROUTE,SIM_ROUTE,AUDIT_ROUTE,WEBHOOK_ROUTE,HEALTH_ROUTE,METRICS_ROUTE api
    class CORS,TENANT,RATE,LOG middleware
    class PARSER,REGISTRY,CONFIG_GEN,FIELD_MAP,DIFF_ENGINE,SIMULATOR,MOCK_SERVER,LIFECYCLE service
    class VAULT,PII,JWT,AUDIT_SVC security
    class DB,UPLOADS data
```

### Field Mapping Strategy Pipeline

```mermaid
flowchart LR
    SOURCE["Source Field<br/>(from BRD)"] --> S1

    subgraph Pipeline["3-Strategy Matching Pipeline"]
        S1["Strategy 1<br/>Exact Synonym Match<br/>(FIELD_SYNONYMS dict)"]
        S2["Strategy 2<br/>Fuzzy String Match<br/>(rapidfuzz token_sort_ratio)"]
        S3["Strategy 3<br/>Partial Token Overlap<br/>(Jaccard similarity)"]
        S1 -->|"No match"| S2
        S2 -->|"Score < 60%"| S3
    end

    S1 -->|"confidence: 1.0"| TARGET["Target Field<br/>(from Adapter Schema)"]
    S2 -->|"confidence: score/100"| TARGET
    S3 -->|"confidence: jaccard"| TARGET
    S3 -->|"No match"| UNMAPPED["Unmapped<br/>(confidence: 0.0)"]

    style SOURCE fill:#3b82f6,stroke:#60a5fa,color:#fff
    style TARGET fill:#10b981,stroke:#34d399,color:#fff
    style UNMAPPED fill:#ef4444,stroke:#f87171,color:#fff
```

---

## 6. API Route Map

### Route Overview

```mermaid
flowchart LR
    subgraph Public["No Auth Required"]
        H["GET /health"]
        M["GET /metrics"]
        D["GET /docs"]
        R["GET /redoc"]
    end

    subgraph V1["API v1 (/api/v1)"]
        subgraph Documents["Documents"]
            D1["POST /documents/upload"]
            D2["GET /documents/"]
            D3["GET /documents/{id}"]
        end

        subgraph Adapters["Adapters"]
            A1["GET /adapters/"]
            A2["GET /adapters/{id}"]
            A3["GET /adapters/{id}/match"]
        end

        subgraph Configurations["Configurations"]
            C1["GET /configurations/templates"]
            C2["POST /configurations/generate"]
            C3["GET /configurations/"]
            C4["GET /configurations/{id}"]
            C5["POST /configurations/{id}/validate"]
            C6["GET /configurations/{id}/diff/{other_id}"]
            C7["GET /configurations/{id}/export"]
        end

        subgraph Simulations["Simulations"]
            S1["POST /simulations/run"]
            S2["GET /simulations/{id}"]
            S3["GET /simulations/{id}/stream"]
        end

        subgraph Audit["Audit"]
            AU1["GET /audit/"]
        end

        subgraph Webhooks["Webhooks"]
            W1["POST /webhooks/"]
            W2["GET /webhooks/"]
            W3["DELETE /webhooks/{id}"]
            W4["POST /webhooks/{id}/test"]
        end
    end
```

### Detailed Endpoint Reference

| Method | Path | Tags | Description | Tenant-Scoped |
|--------|------|------|-------------|:---:|
| `GET` | `/health` | Health | Healthcheck with DB and AI status | No |
| `GET` | `/metrics` | Metrics | In-memory request metrics snapshot | No |
| `POST` | `/api/v1/documents/upload` | Documents | Upload and parse BRD/SOW/spec | Yes |
| `GET` | `/api/v1/documents/` | Documents | List tenant documents | Yes |
| `GET` | `/api/v1/documents/{id}` | Documents | Get document with parsed result | Yes |
| `GET` | `/api/v1/adapters/` | Adapters | List adapters, optional `?category=` | No |
| `GET` | `/api/v1/adapters/{id}` | Adapters | Get adapter with all versions | No |
| `GET` | `/api/v1/adapters/{id}/match` | Adapters | Find adapters matching services | No |
| `GET` | `/api/v1/configurations/templates` | Configurations | List pre-built config templates | No |
| `POST` | `/api/v1/configurations/generate` | Configurations | Generate config from document + adapter | Yes |
| `GET` | `/api/v1/configurations/` | Configurations | List tenant configurations | Yes |
| `GET` | `/api/v1/configurations/{id}` | Configurations | Get configuration detail | Yes |
| `POST` | `/api/v1/configurations/{id}/validate` | Configurations | Validate config completeness | Yes |
| `GET` | `/api/v1/configurations/{a}/diff/{b}` | Configurations | Compare two configurations | Yes |
| `GET` | `/api/v1/configurations/{id}/export` | Configurations | Export as JSON or YAML file | Yes |
| `POST` | `/api/v1/simulations/run` | Simulations | Run simulation against config | Yes |
| `GET` | `/api/v1/simulations/{id}` | Simulations | Get simulation results | Yes |
| `GET` | `/api/v1/simulations/{id}/stream` | Simulations | Stream results via SSE | Yes |
| `GET` | `/api/v1/audit/` | Audit | Query audit logs (paginated) | Yes |
| `POST` | `/api/v1/webhooks/` | Webhooks | Register webhook endpoint | Yes |
| `GET` | `/api/v1/webhooks/` | Webhooks | List tenant webhooks | Yes |
| `DELETE` | `/api/v1/webhooks/{id}` | Webhooks | Delete webhook | Yes |
| `POST` | `/api/v1/webhooks/{id}/test` | Webhooks | Send test event to webhook | Yes |

---

## 7. Security Architecture

```mermaid
flowchart TB
    subgraph Perimeter["Network Perimeter"]
        NGINX["Nginx Reverse Proxy<br/>TLS termination, static serving"]
    end

    subgraph AppSecurity["Application Security"]
        direction TB

        subgraph AuthN["Authentication"]
            TENANT_HDR["X-Tenant-ID Header<br/>(Middleware extraction)"]
            JWT_TOKEN["JWT Tokens<br/>(HS256, configurable expiry)"]
            API_KEY["API Key Auth<br/>(per-adapter)"]
        end

        subgraph AuthZ["Authorization"]
            RBAC["Role-Based Access<br/>admin | configurator | viewer"]
            TENANT_ISO["Row-Level Tenant Isolation<br/>(TenantMixin on 6 tables)"]
        end

        subgraph RateLimit["Rate Limiting"]
            TOKEN_BUCKET["Sliding Window Token Bucket<br/>100 requests / 60 seconds per tenant"]
            EXEMPT["Exempt Paths:<br/>/health, /metrics, /docs, /redoc, /openapi.json"]
        end

        subgraph DataProtection["Data Protection"]
            FERNET["Fernet Symmetric Encryption<br/>SHA-256 derived key from FINSPARK_ENCRYPTION_KEY"]
            PII_MASK["PII Masking Engine"]
            HASH["SHA-256 Hashing<br/>(irreversible value hashing)"]
        end

        subgraph Audit["Audit & Observability"]
            AUDIT_LOG["Immutable Audit Log<br/>actor, action, resource, details, IP, UA"]
            REQ_LOG["Request Logger<br/>method, path, status, duration_ms, tenant_id"]
            METRICS["Metrics Collector<br/>total_requests, per_endpoint, avg_response_time"]
        end
    end

    subgraph DataAtRest["Data at Rest"]
        DB_CREDS["Encrypted Credentials<br/>(Fernet in auth_config column)"]
        WH_SECRETS["Encrypted Webhook Secrets<br/>(Fernet in secret column)"]
        UPLOAD_DIR["Upload Directory<br/>Tenant-partitioned: /uploads/{tenant_id}/"]
    end

    NGINX --> TENANT_HDR
    TENANT_HDR --> RBAC
    RBAC --> TENANT_ISO

    TENANT_HDR --> TOKEN_BUCKET

    FERNET --> DB_CREDS
    FERNET --> WH_SECRETS
    PII_MASK --> REQ_LOG

    classDef perimeter fill:#1e3a5f,stroke:#3b82f6,color:#fff
    classDef auth fill:#1e3a2f,stroke:#10b981,color:#fff
    classDef protect fill:#3a2e1e,stroke:#f59e0b,color:#fff
    classDef audit fill:#3a1e3f,stroke:#a855f7,color:#fff
    classDef data fill:#3a1e1e,stroke:#ef4444,color:#fff

    class NGINX perimeter
    class TENANT_HDR,JWT_TOKEN,API_KEY,RBAC,TENANT_ISO auth
    class TOKEN_BUCKET,EXEMPT,FERNET,PII_MASK,HASH protect
    class AUDIT_LOG,REQ_LOG,METRICS audit
    class DB_CREDS,WH_SECRETS,UPLOAD_DIR data
```

### PII Detection Patterns

| PII Type | Regex Pattern | Mask Output |
|----------|--------------|-------------|
| Aadhaar | `\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b` | `XXXX-XXXX-XXXX` |
| PAN | `\b[A-Z]{5}\d{4}[A-Z]\b` | `XXXXX****X` |
| Phone | `\b(?:\+91[\s-]?)?\d{10}\b` | `XXXXXXXXXX` |
| Email | `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z\|a-z]{2,}\b` | `***@***.***` |
| Account | `\b\d{9,18}\b` | `XXXXXXXXXX` |

### Security Configuration (Environment Variables)

| Variable | Purpose | Default |
|----------|---------|---------|
| `FINSPARK_SECRET_KEY` | JWT signing key | `change-me-in-production-use-openssl-rand-hex-32` |
| `FINSPARK_ENCRYPTION_KEY` | Fernet key derivation seed | `change-me-in-production` |
| `FINSPARK_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `FINSPARK_JWT_EXPIRY_MINUTES` | Token TTL | `60` |
| `FINSPARK_DATABASE_URL` | DB connection string | `sqlite+aiosqlite:///./finspark.db` |

### Middleware Execution Order

Middleware is applied in reverse registration order (last added = first executed):

```
Request  -->  RequestLoggingMiddleware  (logs timing)
         -->  RateLimiterMiddleware     (enforces limits)
         -->  TenantMiddleware          (extracts tenant)
         -->  CORSMiddleware            (CORS headers)
         -->  Route Handler
Response <--  (same stack, reversed)
```
