export interface Adapter {
  id: string;
  name: string;
  type?: string;
  category?: string;
  description?: string;
  status?: "active" | "inactive" | "error";
  is_active?: boolean;
  version?: string;
  versions?: AdapterVersion[];
  icon?: string;
  last_sync?: string;
  created_at?: string;
}

export interface AdapterVersion {
  id: string;
  version: string;
  status: string;
  auth_type: string;
  base_url?: string;
  endpoints?: { path: string; method: string; description?: string }[];
  changelog?: string;
}

export interface Document {
  id: string;
  filename: string;
  content_type?: string;
  file_type?: string;
  doc_type?: string;
  size?: number;
  file_size?: number;
  status: "pending" | "processing" | "completed" | "failed" | "done" | "parsed" | "parsing";
  uploaded_at?: string;
  created_at?: string;
  processed_at?: string;
  parsed_at?: string;
}

export interface Configuration {
  id: string;
  name?: string;
  adapter_type?: string;
  adapter_version_id?: string;
  document_id?: string;
  status: string;
  version?: number;
  created_at: string;
  updated_at: string;
  parameters?: Record<string, unknown>;
  field_mappings?: unknown[];
}

export interface Simulation {
  id: string;
  name?: string;
  configuration_id?: string;
  config_id?: string;
  scenario?: string;
  status: string;
  test_type?: string;
  created_at?: string;
  queued_at?: string;
  completed_at?: string;
  total_tests?: number;
  passed_tests?: number;
  failed_tests?: number;
  duration_ms?: number;
  results?: SimulationResults;
  steps?: unknown[];
}

export interface SimulationResults {
  success_rate: number;
  total_records: number;
  processed_records: number;
  errors: number;
  warnings: number;
  duration_ms: number;
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type?: string;
  resource_type?: string;
  entity_id?: string;
  resource_id?: string;
  user?: string;
  actor?: string;
  actor_email?: string;
  timestamp?: string;
  created_at?: string;
  details?: Record<string, unknown>;
  status?: "success" | "failure" | "warning";
  outcome?: string;
  tenant_id?: string;
}

export interface HealthStatus {
  status: string;
  version?: string;
  env?: string;
  timestamp?: string;
  checks?: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next?: boolean;
}
