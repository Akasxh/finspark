# FinSpark — Feature & UI Connection Tracker

## Ralph Loop Progress

### Backend Features → UI Connection Status

| Feature | Backend | Frontend API | UI | Status |
|---|---|---|---|---|
| Health check | GET /health | healthApi.check | Header indicator | DONE |
| Adapters list | GET /adapters/ | adaptersApi.list | Cards | DONE |
| Adapter detail | GET /adapters/{id} | adaptersApi.get | Modal | DONE |
| Upload document | POST /documents/upload | documentsApi.upload | Dropzone | DONE |
| Document list | GET /documents/ | documentsApi.list | Table | DONE |
| Document detail | GET /documents/{id} | documentsApi.get | Modal (5 tabs) | DONE |
| Delete document | DELETE /documents/{id} | documentsApi.delete | Button + confirm | DONE |
| Generate config | POST /configurations/generate | configurationsApi.generate | Dropdown form | DONE |
| Config list | GET /configurations/ | configurationsApi.list | Expandable rows | DONE |
| Config detail | GET /configurations/{id} | configurationsApi.get | Field mapping table | DONE |
| Validate config | POST /.../validate | configurationsApi.validate | Validate button | DONE |
| Config transition | POST /.../transition | configurationsApi.transition | State buttons | DONE |
| Run simulation | POST /simulations/run | simulationsApi.run | Form + results | DONE |
| Simulation detail | GET /simulations/{id} | simulationsApi.get | Step-by-step view | DONE |
| Audit logs | GET /audit/ | auditApi.list | Timeline | DONE |
| Search | GET /search/ | — | — | NEEDS UI |
| Webhooks CRUD | POST/GET/DELETE /webhooks/ | — | — | NEEDS UI |
| Config templates | GET /configurations/templates | getTemplates | — | NEEDS UI |
| Config export | GET /.../export | — | — | NEEDS UI |
| Config history | GET /.../history | — | — | NEEDS UI |
| Config rollback | POST /.../rollback | — | — | NEEDS UI |
| Dashboard analytics | GET /analytics/dashboard | — | — | NEEDS UI |
| Editable field mappings | — | — | — | NEEDS BOTH |

### Open Issues (10)
- #13 Webhook system (CRITICAL)
- #26 Simulation engine (HIGH)
- #27 Pagination/search (MEDIUM)
- #30 Two config gen systems (MEDIUM)
- #31 Parser quality (MEDIUM)
- #32 Dashboard data (MEDIUM)
- #34 Soft-delete filter (MEDIUM)
- #35 Mobile/accessibility (MEDIUM)
- #36 LLM client async (MEDIUM)
- #38 Diff engine accuracy (MEDIUM)
