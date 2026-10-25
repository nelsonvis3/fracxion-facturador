import { apiRequest, downloadFile } from "./api";
import type { Filters, Page } from "./business-api";
export type ExpenseCategory = { id: string; name: string; is_active: boolean };
export type Expense = { id: string; purchase_order: string | null; supplier: string | null; category: string | null; supplier_name: string; category_name: string; supplier_name_snapshot: string; category_name_snapshot: string; description: string; reference: string; incurred_on: string; due_date: string | null; currency: string; net_amount: string; tax_rate: string; tax_amount: string; total: string; status: "draft" | "posted" | "void"; paid_amount: string; balance: string; has_attachment: boolean; posted_at: string | null; posted_by: string | null; void_reason: string; created_at: string; updated_at: string };
export type ExpensePayload = { purchase_order?: string | null; supplier: string | null; category: string | null; description: string; reference: string; incurred_on: string; due_date: string | null; currency: string; net_amount: string; tax_rate: string; attachment_data?: string; remove_attachment?: boolean };
export type ExpensePayment = { id: string; expense: string; amount: string; method: string; reference: string; paid_at: string; actor: string; created_at: string; reversed_at: string | null; reversal_reason: string };
const base = (tenant: string) => `/api/tenants/${encodeURIComponent(tenant)}`;
const query = (filters: Filters) => new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined && value !== "").map(([key, value]) => [key, String(value)])).toString();
export const expenseApi = {
  list: (tenant: string, filters: Filters = {}) => apiRequest<Page<Expense>>(`${base(tenant)}/expenses/?${query(filters)}`),
  get: (tenant: string, id: string) => apiRequest<Expense>(`${base(tenant)}/expenses/${encodeURIComponent(id)}/`),
  save: (tenant: string, data: Partial<ExpensePayload>, id?: string) => apiRequest<Expense>(`${base(tenant)}/expenses/${id ? `${encodeURIComponent(id)}/` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(data) }),
  register: (tenant: string, id: string) => apiRequest<Expense>(`${base(tenant)}/expenses/${encodeURIComponent(id)}/post/`, { method: "POST", body: "{}" }),
  void: (tenant: string, id: string, reason: string) => apiRequest<Expense>(`${base(tenant)}/expenses/${encodeURIComponent(id)}/void/`, { method: "POST", body: JSON.stringify({ reason }) }),
  categories: (tenant: string, filters: Filters = {}) => apiRequest<Page<ExpenseCategory>>(`${base(tenant)}/expenses/categories/?${query(filters)}`),
  saveCategory: (tenant: string, data: Partial<Omit<ExpenseCategory, "id">>, id?: string) => apiRequest<ExpenseCategory>(`${base(tenant)}/expenses/categories/${id ? `${encodeURIComponent(id)}/` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(data) }),
  payments: (tenant: string, id: string, page = 1) => apiRequest<Page<ExpensePayment>>(`${base(tenant)}/expenses/${encodeURIComponent(id)}/payments/?page=${page}`),
  pay: (tenant: string, id: string, data: { amount: string; method: string; reference: string; paid_at?: string }, key: string) => apiRequest<ExpensePayment>(`${base(tenant)}/expenses/${encodeURIComponent(id)}/payments/`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(data) }),
  reverse: (tenant: string, id: string, reason: string) => apiRequest<ExpensePayment>(`${base(tenant)}/expense-payments/${encodeURIComponent(id)}/reverse/`, { method: "POST", body: JSON.stringify({ reason }) }),
  attachment: (tenant: string, id: string) => downloadFile(`${base(tenant)}/expenses/${encodeURIComponent(id)}/attachment/`, `gasto-${id}.png`),
};
