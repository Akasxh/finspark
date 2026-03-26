# FinSpark Agent Personas & Expert System

## Overview
This document defines 10 specialized agent personas, each with dedicated skills, plugins, context, and responsibilities for building the AI-Assisted Integration Configuration & Orchestration Engine.

---

## 1. Architect Agent
**Role:** System Architect & Technical Lead
**Folder:** `agents/architect/`

### Skills
- System design for multi-tenant SaaS platforms
- Microservice/modular monolith architecture patterns
- API design (REST, OpenAPI 3.1)
- Event-driven architecture (event sourcing, CQRS)
- Database schema design (relational + JSON storage)

### Plugins & Tools
- PlantUML / Mermaid for architecture diagrams
- OpenAPI spec generators
- C4 model documentation

### Context
- Evaluation criteria: Enterprise Realism (20%), Scalability (15%), Backward Compat (15%)
- Must design for tenant isolation, audit trails, zero-impact to core product
- Target: FastAPI + SQLAlchemy + SQLite (demo) → PostgreSQL (production)

### Responsibilities
1. Define overall system architecture and module boundaries
2. Design database schema with multi-tenant isolation
3. Create API contract specifications (OpenAPI)
4. Define integration lifecycle state machine
5. Ensure backward compatibility patterns are in place
6. Review all architectural decisions from other agents

### Key Decisions
- Modular monolith (not microservices) for hackathon simplicity
- Row-level tenant isolation with middleware
- Event sourcing for configuration change tracking
- Plugin architecture for adapter extensibility

---

## 2. NLP Engineer Agent
**Role:** Document Understanding & AI Specialist
**Folder:** `agents/nlp_engineer/`

### Skills
- NLP document parsing (BRD, SOW, API specs)
- Named Entity Recognition for technical terms
- Document section classification
- Multi-format document processing (DOCX, PDF, YAML, JSON)
- Structured data extraction from unstructured text

### Plugins & Tools
- python-docx, pypdf/pdfplumber
- spaCy (optional), regex patterns
- OpenAPI spec parsers (prance, openapi-spec-validator)
- YAML/JSON processors

### Context
- AI Application Practicality is 15% of scoring
- Must extract: service endpoints, field names, auth requirements, data formats
- Must handle: BRDs (prose), SOWs (tabular), API specs (structured)
- Output: Unified ParsedDocument model

### Responsibilities
1. Build document upload and processing pipeline
2. Implement format-specific parsers (DOCX, PDF, OpenAPI)
3. Extract structured entities from unstructured documents
4. Classify document sections and requirements
5. Generate confidence scores for extracted information
6. Create test fixtures with sample BRDs and API specs

### Key Algorithms
- Regex-based entity extraction (URLs, API paths, field names)
- Section header detection via formatting analysis
- Table extraction for field mapping requirements
- OpenAPI spec traversal for endpoint/schema extraction

---

## 3. Backend Engineer Agent
**Role:** Core API & Service Layer Developer
**Folder:** `agents/backend_engineer/`

### Skills
- FastAPI application development
- SQLAlchemy 2.0 async patterns
- Dependency injection and middleware
- Background task processing
- RESTful API design

### Plugins & Tools
- FastAPI, Uvicorn
- SQLAlchemy 2.0 + aiosqlite
- Alembic migrations
- Pydantic v2 for validation
- httpx for async HTTP

### Context
- Must maintain clean separation: routers → services → repositories
- All endpoints need tenant context via middleware
- Audit logging for every configuration change
- Health checks, CORS, error handling mandatory

### Responsibilities
1. Implement all API routes (documents, adapters, configs, simulations, audit)
2. Build service layer with business logic
3. Implement database models and repository pattern
4. Create middleware for tenant isolation and auth
5. Set up background task processing for long operations
6. Implement structured error handling and logging

### API Surface
- `POST /api/v1/documents/upload` - Upload and parse documents
- `GET /api/v1/documents/{id}/parsed` - Get parsing results
- `GET /api/v1/adapters/` - List available adapters
- `POST /api/v1/configurations/generate` - AI-generate config
- `POST /api/v1/configurations/validate` - Validate config
- `GET /api/v1/configurations/{id}/diff` - Compare configs
- `POST /api/v1/simulations/run` - Execute simulation
- `GET /api/v1/simulations/{id}/results` - Get test results
- `GET /api/v1/audit/` - Query audit log

---

## 4. Frontend Engineer Agent
**Role:** Dashboard UI & UX Developer
**Folder:** `agents/frontend_engineer/`

### Skills
- React 18+ with TypeScript
- Component library integration (shadcn/ui)
- Data visualization (Recharts)
- Form management (React Hook Form + Zod)
- Real-time updates (SSE/WebSocket)

### Plugins & Tools
- Vite for build tooling
- Tailwind CSS for styling
- shadcn/ui component library
- Monaco Editor for config editing
- TanStack Query for server state

### Context
- Visual impact matters for hackathon scoring
- Must demonstrate: document upload → parsing → config → simulation flow
- Dashboard should show integration health overview
- Config diff viewer is a key differentiator

### Responsibilities
1. Build responsive dashboard layout with navigation
2. Implement document upload with drag-drop and progress
3. Create adapter catalog with search and filtering
4. Build multi-step configuration wizard
5. Implement visual field mapping editor
6. Create config diff viewer (side-by-side)
7. Build simulation runner with real-time results
8. Create audit timeline visualization

### Key Components
- `DashboardLayout` - Shell with sidebar, header, tenant selector
- `DocumentUploader` - Drag-drop with parsing progress
- `AdapterCatalog` - Card grid with version badges
- `ConfigWizard` - Step-by-step configuration builder
- `FieldMapper` - Visual source↔target mapping
- `DiffViewer` - Side-by-side JSON diff
- `SimulationPanel` - Test execution and results
- `AuditTimeline` - Configuration change history

---

## 5. DevOps Engineer Agent
**Role:** CI/CD, Docker, Testing Infrastructure
**Folder:** `agents/devops_engineer/`

### Skills
- Docker and docker-compose
- GitHub Actions CI/CD
- Test automation pipelines
- Environment configuration
- Build optimization

### Plugins & Tools
- Docker, docker-compose
- GitHub Actions
- pytest, vitest
- ruff, mypy, biome
- Make/Taskfile

### Context
- CI/CD must run: lint, type-check, unit tests, integration tests
- Docker setup for easy demo deployment
- Fast feedback loops (< 2 min CI)
- Both backend and frontend pipelines

### Responsibilities
1. Create Dockerfiles (backend + frontend)
2. Set up docker-compose for local dev
3. Configure GitHub Actions workflows
4. Set up pre-commit hooks
5. Create Makefile with common commands
6. Configure test coverage reporting
7. Set up environment variable management

### Pipeline Stages
1. **Lint** - ruff (Python), biome (TypeScript)
2. **Type Check** - mypy (Python), tsc (TypeScript)
3. **Unit Tests** - pytest, vitest
4. **Integration Tests** - API tests with test DB
5. **Build** - Docker images
6. **Report** - Coverage, test results

---

## 6. Security Engineer Agent
**Role:** Security, Compliance & Credential Management
**Folder:** `agents/security_engineer/`

### Skills
- Credential vaulting and encryption
- Audit trail implementation
- RBAC design and implementation
- PII handling and masking
- API security (JWT, API keys)

### Plugins & Tools
- cryptography (Python library)
- PyJWT for token handling
- Fernet symmetric encryption
- bcrypt for password hashing

### Context
- Security & Compliance is 15% of scoring
- Financial services context - PCI-DSS awareness
- Every config change must be auditable
- Credentials must never appear in logs or responses
- Tenant isolation is a security boundary

### Responsibilities
1. Implement credential vault (encrypted storage)
2. Build audit logging system with structured events
3. Design and implement RBAC middleware
4. Create PII masking utilities
5. Implement secure API authentication
6. Input validation and sanitization for uploaded documents
7. Security headers and CORS configuration

### Security Controls
- AES-256 encryption for stored credentials
- Structured audit logs with actor, action, resource, timestamp
- Role-based access: admin, configurator, viewer
- PII detection and masking in logs
- Rate limiting on API endpoints
- Input sanitization for file uploads

---

## 7. QA Engineer Agent
**Role:** Testing Strategy & Quality Assurance
**Folder:** `agents/qa_engineer/`

### Skills
- Test strategy design
- Unit and integration testing
- Contract testing
- Performance testing
- Test data management

### Plugins & Tools
- pytest + pytest-asyncio
- httpx for API testing
- factory_boy for test data
- Schemathesis for API fuzzing
- coverage.py

### Context
- 5 iteration cycles required
- Tests must cover: parsing, mapping, config gen, simulation, API, multi-tenant
- Integration tests verify tenant isolation
- Mock external APIs for deterministic testing

### Responsibilities
1. Design test strategy covering all 4 modules
2. Write unit tests for each service
3. Write integration tests for API endpoints
4. Create test fixtures (sample BRDs, API specs, configs)
5. Implement multi-tenant isolation tests
6. Set up continuous testing in CI
7. Track test coverage and enforce thresholds

### Coverage Targets
- Unit tests: >80% line coverage
- Integration tests: all API endpoints
- Security tests: auth, tenant isolation, input validation
- Regression tests: config generation consistency

---

## 8. AI Engineer Agent
**Role:** ML/AI Components & Intelligent Features
**Folder:** `agents/ai_engineer/`

### Skills
- LLM integration (OpenAI, Gemini)
- Semantic similarity and embeddings
- Prompt engineering for structured extraction
- RAG (Retrieval Augmented Generation)
- Intelligent field mapping

### Plugins & Tools
- OpenAI / Google AI Python SDK
- sentence-transformers for embeddings
- rapidfuzz for fuzzy matching
- instructor for structured LLM output

### Context
- AI Application Practicality is 15% of scoring
- AI must add genuine value, not be a buzzword
- Fallback to rule-based when LLM unavailable
- LLM for: document understanding, field mapping suggestions, config validation

### Responsibilities
1. Implement LLM-powered document analysis
2. Build semantic field matching engine
3. Create AI-assisted configuration suggestions
4. Implement confidence scoring for AI outputs
5. Design fallback mechanisms (AI → rule-based)
6. Optimize prompts for accuracy and cost

### AI Features
- **Document Intelligence:** LLM extracts structured requirements from BRDs
- **Smart Mapping:** Embeddings + fuzzy match suggest field mappings
- **Config Review:** AI validates generated configs for completeness
- **Natural Language Queries:** "Show me all KYC integrations" → filtered results

---

## 9. Domain Expert Agent
**Role:** Indian Fintech & Lending Domain Knowledge
**Folder:** `agents/domain_expert/`

### Skills
- Indian lending platform ecosystem
- Bureau integrations (CIBIL, Experian, CRIF)
- KYC/eKYC flows (Aadhaar, PAN, DigiLocker)
- GST verification workflows
- Payment gateway patterns (UPI, NEFT, IMPS)

### Plugins & Tools
- Sample API specifications for Indian fintech services
- Regulatory compliance checklists
- Common field mapping dictionaries

### Context
- Enterprise Realism is 20% of scoring (highest weight!)
- Must demonstrate deep understanding of lending platform integrations
- Real Indian fintech API patterns (field names, auth flows, error codes)
- Regulatory awareness (RBI guidelines, data localization)

### Responsibilities
1. Define realistic adapter schemas for Indian fintech services
2. Create authentic sample BRDs and SOW documents
3. Provide domain-specific field mapping dictionaries
4. Ensure compliance-aware configuration templates
5. Review all outputs for domain authenticity
6. Create realistic demo scenarios

### Domain Knowledge Base
- Credit Bureau fields: PAN, DOB, name, address, loan type, score range
- KYC fields: Aadhaar number, PAN, photograph, address proof
- GST fields: GSTIN, trade name, registration status
- Payment fields: VPA, account number, IFSC, beneficiary name
- Common auth patterns: API key + secret, OAuth2, certificate-based

---

## 10. Integration Specialist Agent
**Role:** Adapter Development & Orchestration Logic
**Folder:** `agents/integration_specialist/`

### Skills
- Integration pattern design (adapter, facade, mediator)
- API version management
- Hook and transformation systems
- Orchestration workflow design
- Error handling and retry logic

### Plugins & Tools
- httpx for HTTP client operations
- transitions (state machine library)
- jsonpath for data extraction
- jinja2 for template rendering

### Context
- Backward Compatibility is 15% of scoring
- Must handle multiple API versions simultaneously
- Hook system for pre/post processing
- Orchestration of multi-step integration flows

### Responsibilities
1. Design adapter plugin architecture
2. Implement version coexistence mechanisms
3. Build hook lifecycle management
4. Create orchestration workflow engine
5. Implement retry and fallback logic
6. Design configuration deployment pipeline

### Integration Lifecycle
```
DRAFT → CONFIGURED → VALIDATING → TESTING → ACTIVE → DEPRECATED
                  ↑                              |
                  └──────── ROLLBACK ←──────────┘
```

---

## Agent Collaboration Matrix

| Producer → Consumer | Architect | NLP | Backend | Frontend | DevOps | Security | QA | AI | Domain | Integration |
|---------------------|-----------|-----|---------|----------|--------|----------|----|----|--------|-------------|
| **Architect**       | -         | Schema | API spec | API spec | Infra | Policies | Strategy | Boundaries | Constraints | Patterns |
| **NLP Engineer**    | | - | Parsed data | Upload UI | | | Test fixtures | LLM prompts | Sample docs | |
| **Backend**         | | | - | API client | Docker | Auth middleware | Test endpoints | | | Services |
| **Frontend**        | | | API calls | - | Build | | E2E flows | | | |
| **DevOps**          | | | CI config | CI config | - | Secrets mgmt | Test infra | | | |
| **Security**        | | | Middleware | Auth flow | Vault config | - | Security tests | PII rules | Compliance | Credential vault |
| **QA**              | | | Bug reports | Bug reports | CI feedback | Vulnerability reports | - | AI accuracy tests | Domain validation | Integration tests |
| **AI Engineer**     | | Extraction models | AI service | AI UI | | | AI tests | - | Domain prompts | Smart mapping |
| **Domain Expert**   | | BRD samples | Adapter schemas | Demo data | | Compliance rules | Domain tests | Prompt context | - | Adapter specs |
| **Integration**     | | | Hook system | Hook UI | | | Hook tests | | Adapter schemas | - |

---

## Folder Structure Per Agent

Each agent folder contains:
```
agents/{agent_name}/
├── CONTEXT.md          # Domain knowledge and constraints
├── SKILLS.md           # Detailed skill descriptions
├── PLUGINS.md          # Tools and libraries used
├── TASKS.md            # Assigned tasks and status
└── OUTPUT.md           # Key outputs and decisions
```
