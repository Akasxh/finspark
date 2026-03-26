export interface Adapter {
  id: string;
  name: string;
  type: string;
  description: string;
  status: "active" | "inactive" | "error";
  version: string;
  last_sync?: string;
  config?: Record<string, unknown>;
}

export interface Document {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  status: "pending" | "processing" | "completed" | "failed";
  uploaded_at: string;
  processed_at?: string;
  metadata?: Record<string, unknown>;
}

export interface Configuration {
  id: string;
  name: string;
  adapter_type: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
  parameters: Record<string, unknown>;
}

export interface Simulation {
  id: string;
  name: string;
  configuration_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  completed_at?: string;
  results?: SimulationResults;
}

export interface SimulationResults {
  success_rate: number;
  total_records: number;
  processed_records: number;
  errors: number;
  warnings: number;
  duration_ms: number;
  details?: Record<string, unknown>[];
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  user: string;
  timestamp: string;
  details?: Record<string, unknown>;
  status: "success" | "failure" | "warning";
}

export interface HealthStatus {
  status: string;
  version?: string;
  uptime?: number;
  services?: Record<string, string>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
