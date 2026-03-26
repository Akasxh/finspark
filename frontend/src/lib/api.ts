import axios from "axios";
import type {
  Adapter,
  AuditEntry,
  Configuration,
  Document,
  HealthStatus,
  Simulation,
} from "@/types";

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
  },
);

export const healthApi = {
  check: () => api.get<HealthStatus>("/health").then((r) => r.data),
};

export const adaptersApi = {
  list: () => api.get<Adapter[]>("/api/v1/adapters/").then((r) => r.data),
};

export const documentsApi = {
  list: () => api.get<Document[]>("/api/v1/documents/").then((r) => r.data),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<Document>("/api/v1/documents/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
};

export const configurationsApi = {
  list: () =>
    api.get<Configuration[]>("/api/v1/configurations/").then((r) => r.data),
  generate: (params: { name: string; adapter_type: string }) =>
    api
      .post<Configuration>("/api/v1/configurations/generate", params)
      .then((r) => r.data),
};

export const simulationsApi = {
  list: () =>
    api.get<Simulation[]>("/api/v1/simulations/").then((r) => r.data),
  run: (params: { name: string; configuration_id: string }) =>
    api
      .post<Simulation>("/api/v1/simulations/run", params)
      .then((r) => r.data),
};

export const auditApi = {
  list: () => api.get<AuditEntry[]>("/api/v1/audit/").then((r) => r.data),
};

export default api;
