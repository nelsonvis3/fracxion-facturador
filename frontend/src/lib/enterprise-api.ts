import { apiRequest, type AuthUser, type Tenant } from "./api";
import type { Page } from "./business-api";

export const roleLabels: Record<Tenant["role"], string> = { owner: "Propietario", admin: "Administrador", accountant: "Contador", sales: "Ventas", viewer: "Solo lectura" };
export type BusinessSettings = {
  name: string; legal_name: string; tax_id: string; country_code: string; timezone: string;
  default_currency: string; contact_email: string; contact_phone: string; address: string;
  website: string; payment_terms_days: number | null; invoice_footer: string;
  payment_reminders_enabled: boolean; has_logo: boolean; logo_updated_at: string | null;
};
export type Member = { id: string; email: string; first_name: string; last_name: string; role: Tenant["role"]; is_active: boolean; user_active: boolean; created_at: string };
export type Invitation = { id: string; email: string; role: Tenant["role"]; state: "pending" | "accepted" | "revoked" | "expired"; delivery_status: "pending" | "sent" | "failed"; expires_at: string; sent_at: string | null; created_at: string };
const path = (tenant: string) => `/api/tenants/${encodeURIComponent(tenant)}`;
export const enterpriseApi = {
  settings: (tenant: string) => apiRequest<BusinessSettings>(`${path(tenant)}/settings/`),
  updateSettings: (tenant: string, data: Partial<BusinessSettings> & { logo_data?: string; remove_logo?: boolean }) => apiRequest<BusinessSettings>(`${path(tenant)}/settings/`, { method: "PATCH", body: JSON.stringify(data) }),
  logoUrl: (tenant: string, version?: string | null) => `${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}${path(tenant)}/settings/logo/?v=${encodeURIComponent(version ?? "")}`,
  members: (tenant: string, page = 1) => apiRequest<Page<Member>>(`${path(tenant)}/members/?page=${page}`),
  updateMember: (tenant: string, id: string, data: Partial<Pick<Member, "role" | "is_active">>) => apiRequest<Member>(`${path(tenant)}/members/${encodeURIComponent(id)}/`, { method: "PATCH", body: JSON.stringify(data) }),
  invitations: (tenant: string, page = 1) => apiRequest<Page<Invitation>>(`${path(tenant)}/invitations/?page=${page}`),
  invite: (tenant: string, email: string, role: Tenant["role"]) => apiRequest<Invitation>(`${path(tenant)}/invitations/`, { method: "POST", body: JSON.stringify({ email, role }) }),
  manageInvitation: (tenant: string, id: string, action: "resend" | "revoke") => apiRequest<Invitation>(`${path(tenant)}/invitations/${encodeURIComponent(id)}/${action}/`, { method: "POST", body: "{}" }),
  previewInvitation: (token: string) => apiRequest<{ company_name: string; email: string; role: Tenant["role"]; expires_at: string; account_exists: boolean }>("/api/auth/invitations/preview/", { method: "POST", body: JSON.stringify({ token }) }),
  acceptInvitation: (data: { token: string; first_name?: string; last_name?: string; password?: string; password_confirm?: string }) => apiRequest<{ user: AuthUser; tenant: Tenant }>("/api/auth/invitations/accept/", { method: "POST", body: JSON.stringify(data) }),
};

export function companyDate(timezone: string, offsetDays = 0) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const read = (type: string) => parts.find(p => p.type === type)!.value;
  const date = new Date(`${read("year")}-${read("month")}-${read("day")}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}
