import { apiRequest } from "./api";
import type { Filters, Page } from "./business-api";

export type Purchase = { id: string; supplier: string; supplier_name: string; supplier_name_snapshot: string; reference: string; notes: string; currency: string; expected_on: string | null; status: "draft" | "ordered" | "closed" | "cancelled"; net_amount: string; tax_amount: string; total: string; confirmed_at: string | null; closed_at: string | null; close_reason: string; created_at: string };
export type PurchaseLineInput = { product: string; quantity: string; unit_cost: string; tax_rate: string };
export type PurchasePayload = { supplier: string; currency: string; reference: string; notes: string; expected_on: string | null; lines: PurchaseLineInput[] };
export type PurchaseLine = PurchaseLineInput & { id: string; position: number; product_name_snapshot: string; product_type_snapshot: string; unit_snapshot: string; received_quantity: string; remaining_quantity: string; net_amount: string; tax_amount: string; total: string };
export type PurchaseReceipt = { id: string; order: string; reference: string; actor: string; occurred_at: string; lines: { id: string; line: string; quantity: string; movement: string | null }[]; reversal: string | null; reversal_reason: string };
const base = (tenant: string) => `/api/tenants/${encodeURIComponent(tenant)}/purchases/`;
const detail = (tenant: string, id: string) => `${base(tenant)}${encodeURIComponent(id)}/`;
const query = (filters: Filters) => new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==undefined&&value!=="").map(([key,value])=>[key,String(value)])).toString();
export const purchaseStatus = { draft: "Borrador", ordered: "Pedido confirmado", closed: "Cerrado", cancelled: "Cancelado" };
export const purchaseApi = {
  list: (tenant: string, filters: Filters = {}) => apiRequest<Page<Purchase>>(`${base(tenant)}?${query(filters)}`),
  get: (tenant: string, id: string) => apiRequest<Purchase>(detail(tenant,id)),
  save: (tenant: string, data: Partial<PurchasePayload>, id?: string) => apiRequest<Purchase>(id?detail(tenant,id):base(tenant),{method:id?"PATCH":"POST",body:JSON.stringify(data)}),
  confirm: (tenant: string, id: string) => apiRequest<Purchase>(`${detail(tenant,id)}confirm/`,{method:"POST",body:"{}"}),
  close: (tenant: string, id: string, reason: string) => apiRequest<Purchase>(`${detail(tenant,id)}close/`,{method:"POST",body:JSON.stringify({reason})}),
  lines: (tenant: string, id: string) => apiRequest<PurchaseLine[]>(`${detail(tenant,id)}lines/`),
  receipts: (tenant: string, id: string, page = 1) => apiRequest<Page<PurchaseReceipt>>(`${detail(tenant,id)}receipts/?page=${page}`),
  receive: (tenant: string, id: string, data: { reference: string; lines: { line: string; quantity: string }[] }, key: string) => apiRequest<PurchaseReceipt>(`${detail(tenant,id)}receipts/`,{method:"POST",headers:{"Idempotency-Key":key},body:JSON.stringify(data)}),
  reverse: (tenant: string, id: string, reason: string) => apiRequest<PurchaseReceipt>(`/api/tenants/${encodeURIComponent(tenant)}/purchase-receipts/${encodeURIComponent(id)}/reverse/`,{method:"POST",body:JSON.stringify({reason})}),
};
