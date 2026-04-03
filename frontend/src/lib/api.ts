import type {
  Adapter,
  AuditEntry,
  Configuration,
  Document,
  HealthStatus,
  Simulation,
} from "@/types";
import axios from "axios";

const api = axios.create({
  baseURL: "",
  headers: {
    "Content-Type": "application/json",
    "X-Tenant-ID": "default",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      console.error("[API Error]", error.response?.status, error.message);
    }
    return Promise.reject(error);
  }
);

export const healthApi = {
  check: () => api.get<HealthStatus>("/health").then((r) => r.data),
};

export const adaptersApi = {
  list: () =>
    api
      .get<{ data: { adapters: Adapter[]; total: number; categories: string[] } }>(
        "/api/v1/adapters/"
      )
      .then((r) => r.data.data.adapters),
};

export const documentsApi = {
  list: () => api.get("/api/v1/documents/").then((r) => (r.data.data ?? []) as Document[]),
  upload: (file: File) => {
    const docType = "brd";
    const form = new FormData();
    form.append("file", file);
    return api
      .post(`/api/v1/documents/upload?doc_type=${docType}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data.data as Document);
  },
};

export const configurationsApi = {
  list: () =>
    api.get("/api/v1/configurations/").then((r) => (r.data.data ?? []) as Configuration[]),
  generate: (params: { name: string; adapter_type: string }) =>
    api
      .post("/api/v1/configurations/generate", {
        name: params.name,
        document_id: "",
        adapter_version_id: "",
      })
      .then((r) => r.data.data as Configuration),
};

export const simulationsApi = {
  list: () =>
    api.get("/api/v1/simulations/").then((r) => {
      const data = r.data.data;
      if (Array.isArray(data)) return data as Simulation[];
      if (data?.items) return data.items as Simulation[];
      return [] as Simulation[];
    }),
  run: (params: { name: string; configuration_id: string }) =>
    api
      .post("/api/v1/simulations/run", {
        configuration_id: params.configuration_id,
        test_type: "smoke",
      })
      .then((r) => r.data.data as Simulation),
};

export const auditApi = {
  list: () =>
    api.get("/api/v1/audit/").then((r) => {
      const data = r.data.data;
      if (Array.isArray(data)) return data as AuditEntry[];
      if (data?.items) return data.items as AuditEntry[];
      return [] as AuditEntry[];
    }),
};

export default api;
