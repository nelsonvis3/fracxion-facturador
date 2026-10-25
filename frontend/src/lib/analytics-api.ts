import { apiRequest } from "./api";
export const canAnalyze = (role: string) => ["owner", "admin", "accountant"].includes(role);
export type AnalyticsFilters = { date_from: string; date_to: string; currency: string; customer?: string };
export type Metrics = { invoiced: string; collected: string; outstanding: string; overdue: string; issued_count: number; unpaid_count: number; unscheduled_count: number; overpaid_count: number };
export type Analytics = {
  company: { id: string; name: string }; filters: AnalyticsFilters; timezone: string; as_of: string; balance_basis: string;
  metrics: Metrics; previous: { date_from: string; date_to: string; metrics: Metrics };
  monthly: { month: string; invoiced: string; collected: string }[];
  customers: { id: string; name: string; invoiced: string }[];
  products: { id: string | null; name: string; sku: string; invoiced: string; quantity: string }[];
  payment_methods: { method: string; label: string; collected: string; count: number }[];
  aging: { bucket: string; balance: string; count: number }[];
};
export const analyticsApi = {
  overview: (tenant: string, filters: AnalyticsFilters) => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => !!value));
    return apiRequest<Analytics>(`/api/tenants/${encodeURIComponent(tenant)}/analytics/overview/?${params}`);
  },
  counts: (tenant: string) => apiRequest<{ customers: number; products: number; drafts: number; issued: number }>(`/api/tenants/${encodeURIComponent(tenant)}/analytics/records/`),
};
