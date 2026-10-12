import { apiRequest, type Customer, type Tenant } from "./api";

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };
export type Filters = Record<string, string | number | boolean | undefined>;
export type ReferenceOption = { code: string; name: string };
export const referenceApi = {
  countries: () => apiRequest<{ results: ReferenceOption[] }>("/api/reference/countries/"),
  subdivisions: (code: string) => apiRequest<{ results: ReferenceOption[] }>(`/api/reference/countries/${encodeURIComponent(code)}/subdivisions/`),
};

function path(tenant: string, resource: string, id?: string) {
  return `/api/tenants/${encodeURIComponent(tenant)}/${resource}/${id ? `${encodeURIComponent(id)}/` : ""}`;
}
function query(filters: Filters = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.size ? `?${params}` : "";
}
export type Product = {
  id: string; tenant: string; name: string; sku: string | null; description: string;
  product_type: "product" | "service"; unit: "unit" | "hour" | "kg" | "liter" | "meter" | "pack";
  unit_price: string; currency: string; tax_rate: string; is_active: boolean;
  created_at: string; updated_at: string;
};
export type ProductPayload = Omit<Product, "id" | "tenant" | "created_at" | "updated_at">;
export const productApi = {
  list: (tenant: string, filters?: Filters) => apiRequest<Page<Product>>(path(tenant, "products") + query(filters)),
  create: (tenant: string, payload: ProductPayload) => apiRequest<Product>(path(tenant, "products"), { method: "POST", body: JSON.stringify(payload) }),
  update: (tenant: string, id: string, payload: Partial<ProductPayload>) => apiRequest<Product>(path(tenant, "products", id), { method: "PATCH", body: JSON.stringify(payload) }),
  deactivate: (tenant: string, id: string) => apiRequest<Product>(path(tenant, "products", id) + "deactivate/", { method: "POST", body: "{}" }),
};
export type InvoiceLine = {
  id: string; position: number; product: string | null; description_snapshot: string;
  sku_snapshot: string; unit_snapshot: string; quantity: string; unit_price: string;
  tax_rate: string; subtotal: string; tax_amount: string; total: string;
};
export type Invoice = {
  id: string; tenant: string; customer: string; status: "draft" | "issued";
  document_kind: "invoice" | "credit_note" | "debit_note"; internal_number: number | null;
  currency: string; customer_name_snapshot: string; customer_legal_name_snapshot: string;
  customer_document_type_snapshot: string; customer_document_number_snapshot: string;
  customer_address_snapshot: string; customer_city_snapshot: string; customer_province_snapshot: string;
  customer_email_snapshot: string; customer_country_code_snapshot: string; customer_postal_code_snapshot: string;
  subtotal: string; tax_total: string; total: string; paid_total: string; balance: string;
  notes: string; created_by: string | null; issued_by: string | null; issued_at: string | null;
  created_at: string; updated_at: string; lines: InvoiceLine[];
};
export type InvoiceDraft = { customer: string; currency: string; notes?: string; lines: { product: string; quantity: string }[] };
export const invoiceApi = {
  list: (tenant: string, filters?: Filters) => apiRequest<Page<Invoice>>(path(tenant, "invoices") + query(filters)),
  get: (tenant: string, id: string) => apiRequest<Invoice>(path(tenant, "invoices", id)),
  create: (tenant: string, payload: InvoiceDraft) => apiRequest<Invoice>(path(tenant, "invoices"), { method: "POST", body: JSON.stringify(payload) }),
  issue: (tenant: string, id: string) => apiRequest<Invoice>(path(tenant, "invoices", id) + "issue/", { method: "POST", body: "{}" }),
};
export type PaymentMethod = "cash" | "bank_transfer" | "debit_card" | "credit_card" | "digital_wallet" | "check" | "other";
export type Payment = {
  id: string; tenant: string; invoice: string; recorded_by: string | null;
  method: PaymentMethod; method_label: string; amount: string; external_reference: string | null;
  currency: string; invoice_number: number | null; customer_name: string;
  received_at: string; created_at: string; notes: string;
  reversal: { id: string; reason: string; reversed_by: string | null; occurred_at: string } | null;
};
export type PaymentPayload = { invoice: string; method: PaymentMethod; amount: string; external_reference?: string; received_at?: string; notes?: string };
export const paymentApi = {
  list: (tenant: string, filters?: Filters) => apiRequest<Page<Payment>>(path(tenant, "payments") + query(filters)),
  create: (tenant: string, payload: PaymentPayload) => apiRequest<Payment>(path(tenant, "payments"), { method: "POST", body: JSON.stringify(payload) }),
  reverse: (tenant: string, id: string, reason: string) => apiRequest<NonNullable<Payment["reversal"]>>(path(tenant, "payments", id) + "reverse/", { method: "POST", body: JSON.stringify({ reason }) }),
};
export type AuditEvent = {
  id: string; actor: string | null; action: string; action_label: string; entity_type: string;
  entity_id: string; changes: Record<string, unknown>; metadata: Record<string, unknown>; occurred_at: string;
};
export const auditApi = {
  list: (tenant: string, filters?: Filters) => apiRequest<Page<AuditEvent>>(path(tenant, "audit-events") + query(filters)),
};
export const canManage = (role: Tenant["role"]) => role === "owner" || role === "admin";
export const canRecordPayment = (role: Tenant["role"]) => canManage(role) || role === "accountant";

// Solo texto presentado al usuario. Ningún cálculo contable usa Number en el cliente.
export function money(value: string, currency: string) {
  const [integer, fraction = "00"] = value.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${currency} ${grouped},${fraction.padEnd(2, "0").slice(0, 2)}`;
}
export const dateTime = (value: string) => new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Argentina/Cordoba" }).format(new Date(value));
export const invoiceLabel = (invoice: Pick<Invoice, "internal_number">) => invoice.internal_number ? `Interna #${invoice.internal_number}` : "Borrador";
export type CustomerOption = Pick<Customer, "id" | "name" | "document_number">;
