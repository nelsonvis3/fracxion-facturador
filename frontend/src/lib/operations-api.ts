import { apiRequest } from "./api";
import type { Filters, Page } from "./business-api";
export type Supplier = { id: string; name: string; legal_name: string; tax_id: string; country_code: string; email: string; phone: string; address: string; notes: string; is_active: boolean; created_at: string; updated_at: string };
export type SupplierPayload = Omit<Supplier, "id" | "created_at" | "updated_at">;
export type InventoryItem = { id: string; name: string; sku: string | null; unit: string; is_active: boolean; balance: string; minimum: string; tracking: boolean; low_stock: boolean };
export type Movement = { id: string; product: string; kind: "in" | "out" | "adjustment" | "reversal"; delta: string; balance_after: string; reason: string; reference: string; product_name_snapshot: string; unit_snapshot: string; actor: string; reverses: string | null; reversed_by: string | null; occurred_at: string };
export type MovementPayload = { product: string; kind: "in" | "out" | "adjustment"; quantity: string; reason: string; reference: string };
const path = (tenant: string, resource: string, id?: string) => `/api/tenants/${encodeURIComponent(tenant)}/${resource}/${id ? `${encodeURIComponent(id)}/` : ""}`;
const query = (filters: Filters) => new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined && value !== "").map(([key, value]) => [key, String(value)])).toString();
export const operationsApi = {
  suppliers: (tenant: string, filters: Filters = {}) => apiRequest<Page<Supplier>>(`${path(tenant, "suppliers")}?${query(filters)}`),
  saveSupplier: (tenant: string, data: Partial<SupplierPayload>, id?: string) => apiRequest<Supplier>(path(tenant, "suppliers", id), { method: id ? "PATCH" : "POST", body: JSON.stringify(data) }),
  items: (tenant: string, filters: Filters = {}) => apiRequest<Page<InventoryItem>>(`${path(tenant, "inventory/items")}?${query(filters)}`),
  policy: (tenant: string, id: string, data: { tracking: boolean; minimum: string }) => apiRequest<InventoryItem>(path(tenant, "inventory/items", id), { method: "PATCH", body: JSON.stringify(data) }),
  movements: (tenant: string, filters: Filters = {}) => apiRequest<Page<Movement>>(`${path(tenant, "inventory/movements")}?${query(filters)}`),
  move: (tenant: string, data: MovementPayload, key: string) => apiRequest<Movement>(path(tenant, "inventory/movements"), { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(data) }),
  reverse: (tenant: string, id: string, reason: string, key: string) => apiRequest<Movement>(`${path(tenant, "inventory/movements", id)}reverse/`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ reason }) }),
};
