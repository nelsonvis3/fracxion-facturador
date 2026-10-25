import { apiRequest, downloadFile } from "./api";
import type { Page } from "./business-api";
import type { AnalyticsFilters } from "./analytics-api";

export type ReportKind = "sales" | "payments" | "receivables" | "customers" | "products" | "summary" | "expenses" | "payables";
export type FileFormat = "csv" | "xlsx" | "pdf";
export type ReportParams = Partial<AnalyticsFilters> & { kind: ReportKind; file_format: FileFormat; supplier?: string };
export const reportLabels: Record<ReportKind, string> = { sales: "Resumen de ventas internas", payments: "Informe de cobros", receivables: "Cuentas por cobrar", customers: "Movimientos por cliente", products: "Facturación por producto", summary: "Resumen financiero interno", expenses: "Gastos registrados", payables: "Cuentas por pagar" };
export type Job = {
  id: string; kind: "report" | "reminders"; payload: Partial<ReportParams>; status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  attempts: number; available_at: string; started_at: string | null; finished_at: string | null; error_code: string;
  result_format: string; result_filename: string; result_expires_at: string | null; created_at: string; rule: string | null;
  executions: { number: number; started_at: string; finished_at: string | null; outcome: string }[];
};
export type Rule = { id: string; name: string; kind: "report" | "reminders"; frequency: "daily" | "weekly" | "monthly"; hour: number; enabled: boolean; options: Partial<ReportParams>; next_run_at: string; last_run_at: string | null; created_at: string };
export type Notification = { id: string; title: string; message: string; invoice: string | null; job: string | null; read_at: string | null; created_at: string };
const base = (tenant: string) => `/api/tenants/${encodeURIComponent(tenant)}`;
export const automationApi = {
  jobs: (tenant: string, page = 1) => apiRequest<Page<Job>>(`${base(tenant)}/reports/jobs/?page=${page}`),
  generate: (tenant: string, params: ReportParams) => apiRequest<Job>(`${base(tenant)}/reports/jobs/`, { method: "POST", body: JSON.stringify(params) }),
  retry: (tenant: string, id: string) => apiRequest<Job>(`${base(tenant)}/reports/jobs/${encodeURIComponent(id)}/retry/`, { method: "POST", body: "{}" }),
  download: (tenant: string, job: Job) => downloadFile(`${base(tenant)}/reports/jobs/${encodeURIComponent(job.id)}/download/`, job.result_filename),
  immediate: (tenant: string, params: ReportParams) => downloadFile(`${base(tenant)}/reports/export/?${new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined) as [string, string][]).toString()}`, `fracxion-${params.kind}.${params.file_format}`),
  rules: (tenant: string, page = 1) => apiRequest<Page<Rule>>(`${base(tenant)}/automation/rules/?page=${page}`),
  saveRule: (tenant: string, data: Partial<Rule>, id?: string) => apiRequest<Rule>(`${base(tenant)}/automation/rules/${id ? `${encodeURIComponent(id)}/` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(data) }),
  notifications: (tenant: string, page = 1, unread = false) => apiRequest<Page<Notification>>(`${base(tenant)}/notifications/?page=${page}&unread=${unread}`),
  read: (tenant: string, id: string) => apiRequest<Notification>(`${base(tenant)}/notifications/${encodeURIComponent(id)}/read/`, { method: "POST", body: "{}" }),
};
