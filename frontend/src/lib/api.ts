const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? ""
).replace(/\/+$/, "");

export type AuthUser = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
};

export type AuthResponse = {
  user: AuthUser;
  csrfToken?: string;
};

export type DetailResponse = {
  detail: string;
};

export type RegistrationPayload = {
  first_name: string;
  last_name?: string;
  company_name: string;
  email: string;
  password: string;
  password_confirm: string;
};

export type RegistrationResponse = AuthResponse & { tenant: Tenant };

export type PasswordResetConfirmation = {
  uid: string;
  token: string;
  password: string;
  password_confirm: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let redirectingToLogin = false;

export function redirectToLogin() {
  if (typeof window !== "undefined" && !redirectingToLogin) {
    redirectingToLogin = true;
    // Un documento nuevo descarta los datos privados retenidos por React Activity.
    window.location.replace("/");
  }
}

export function readErrorMessage(body: unknown): string {
  if (body && typeof body === "object") {
    const data = body as Record<string, unknown>;

    if (typeof data.detail === "string") {
      return data.detail;
    }

    for (const value of Object.values(data)) {
      if (typeof value === "string") {
        return value;
      }
      if (value && typeof value === "object") {
        const nested = readErrorMessage(value);
        if (nested !== "No se pudo completar la solicitud.") return nested;
      }

      if (Array.isArray(value)) {
        const message = value.find(
          (item): item is string => typeof item === "string",
        );

        if (message) {
          return message;
        }
      }
    }
  }

  return "No se pudo completar la solicitud.";
}

// Leer el token JSON funciona también con cookies HttpOnly y API en otro host.
// Se obtiene antes de cada mutación para respetar rotaciones en otras pestañas.
async function getCsrfToken(): Promise<string> {

  const response = await fetch(
    `${API_BASE_URL}/api/auth/csrf/`,
    {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new ApiError(
      "No se pudo iniciar la protección CSRF.",
      response.status,
      null,
    );
  }

  const body = await response.json() as { csrfToken?: string };
  if (!body.csrfToken) throw new ApiError("El servidor no entregó el token CSRF.", 403, body);
  return body.csrfToken;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const safeMethods = ["GET", "HEAD", "OPTIONS"];

  if (!safeMethods.includes(method)) {
    headers.set("X-CSRFToken", await getCsrfToken());
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  let body: unknown = null;

  if (response.status !== 204) {
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined" && (window.location.pathname.startsWith("/dashboard") || window.location.pathname.startsWith("/account/"))) {
      redirectToLogin();
    }
    throw new ApiError(
      readErrorMessage(body),
      response.status,
      body,
    );
  }

  if (body === null && response.status !== 204) {
    throw new ApiError("El servidor devolvió una respuesta inesperada.", 502, null);
  }

  if (!safeMethods.includes(method) && path.startsWith("/api/tenants/") && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("fracxion:business-change", { detail: { tenantId: path.split("/")[3] } }));
  }
  return body as T;
}

export async function downloadFile(path: string, filename: string) {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include", cache: "no-store" });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    if (response.status === 401) redirectToLogin();
    throw new ApiError(readErrorMessage(body), response.status, body);
  }
  const file = await response.blob();
  const url = URL.createObjectURL(file);
  const link = document.createElement("a"); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  // Keep the URL alive until the browser has consumed the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export const authApi = {
  register(data: RegistrationPayload): Promise<RegistrationResponse> {
    return apiRequest<RegistrationResponse>("/api/auth/register/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  currentUser(): Promise<AuthResponse> {
    return apiRequest<AuthResponse>("/api/auth/me/");
  },

  mfaLogin(code: string): Promise<AuthResponse> {
    return apiRequest<AuthResponse>("/api/auth/mfa/login/", {method: "POST", body: JSON.stringify({code})});
  },

  login(email: string, password: string): Promise<AuthResponse | {mfa_required:true;expires_in:number;csrfToken:string}> {
    return apiRequest<AuthResponse | {mfa_required:true;expires_in:number;csrfToken:string}>(
      "/api/auth/login/",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
    );
  },

  async logout(afterLogout?: () => Promise<void>): Promise<DetailResponse> {
    const response = await apiRequest<DetailResponse>(
      "/api/auth/logout/",
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
    // The session is already revoked. Always discard the old document, even if
    // a presentation callback fails; animations must not determine security.
    try {
      await afterLogout?.();
    } finally {
      redirectToLogin();
    }
    return response;
  },

  requestPasswordReset(email: string): Promise<DetailResponse> {
    return apiRequest<DetailResponse>(
      "/api/auth/password-reset/",
      {
        method: "POST",
        body: JSON.stringify({ email }),
      },
    );
  },

  confirmPasswordReset(
    data: PasswordResetConfirmation,
  ): Promise<DetailResponse> {
    return apiRequest<DetailResponse>(
      "/api/auth/password-reset/confirm/",
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );
  },
};

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  role: "owner" | "admin" | "accountant" | "sales" | "viewer";
};

export const tenantApi = {
  getMine: () =>
    apiRequest<{ results: Tenant[] }>("/api/auth/tenants/"),
};

export type CustomerType = "individual" | "company";

export type CustomerDocumentType = "" | "cuit" | "cuil" | "dni" | "other";

export type Customer = {
  id: string;
  tenant: string;
  customer_type: CustomerType;
  name: string;
  legal_name: string;
  document_type: CustomerDocumentType;
  document_number: string | null;
  email: string;
  phone: string;
  address: string;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  notes: string;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomerPayload = {
  customer_type: CustomerType;
  name: string;
  legal_name?: string;
  document_type?: CustomerDocumentType;
  document_number?: string | null;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  country_code?: string;
  notes?: string;
  is_active?: boolean;
};

export type CustomerFilters = {
  search?: string;
  customer_type?: CustomerType;
  document_type?: CustomerDocumentType;
  is_active?: boolean;
  province?: string;
  ordering?: "name" | "-name" | "created_at" | "-created_at";
  page?: number;
};

export type CustomerListResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Customer[];
};

export const customerApi = {
  list(
    tenantId: string,
    filters: CustomerFilters = {},
  ): Promise<CustomerListResponse> {
    const params = new URLSearchParams();

    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== "") {
        params.set(key, String(value));
      }
    }

    const query = params.toString();
    const path = `/api/tenants/${encodeURIComponent(tenantId)}/customers/`;

    return apiRequest<CustomerListResponse>(
      query ? `${path}?${query}` : path,
    );
  },

  get(tenantId: string, customerId: string): Promise<Customer> {
    return apiRequest<Customer>(
      `/api/tenants/${encodeURIComponent(tenantId)}/customers/${encodeURIComponent(customerId)}/`,
    );
  },

  create(
    tenantId: string,
    data: CustomerPayload,
  ): Promise<Customer> {
    return apiRequest<Customer>(
      `/api/tenants/${encodeURIComponent(tenantId)}/customers/`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );
  },

  update(
    tenantId: string,
    customerId: string,
    data: Partial<CustomerPayload>,
  ): Promise<Customer> {
    return apiRequest<Customer>(
      `/api/tenants/${encodeURIComponent(tenantId)}/customers/${encodeURIComponent(customerId)}/`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    );
  },

  deactivate(
    tenantId: string,
    customerId: string,
  ): Promise<Customer> {
    return apiRequest<Customer>(
      `/api/tenants/${encodeURIComponent(tenantId)}/customers/${encodeURIComponent(customerId)}/deactivate/`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },
};
