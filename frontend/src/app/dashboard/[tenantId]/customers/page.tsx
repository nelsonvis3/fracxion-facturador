
"use client";

import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  UserRound,
  UserX,
} from "lucide-react";

import {
  ApiError,
  customerApi,
  redirectToLogin,
  type Customer,
  type CustomerDocumentType,
  type CustomerFilters,
  type CustomerPayload,
  type CustomerType,
} from "@/lib/api";

import { canManage, referenceApi, type ReferenceOption } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { Modal } from "@/components/business-ui";

type CustomerFormData = {
  customer_type: CustomerType;
  name: string;
  legal_name: string;
  document_type: CustomerDocumentType;
  document_number: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  notes: string;
};

const newCustomerForm = (): CustomerFormData => ({
  customer_type: "individual",
  name: "",
  legal_name: "",
  document_type: "",
  document_number: "",
  email: "",
  phone: "",
  address: "",
  city: "",
  province: "",
  postal_code: "",
  country_code: "AR",
  notes: "",
});

const inputClass =
  "mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

const labelClass = "block text-sm font-medium text-slate-700";

function validateCustomerForm(form: CustomerFormData): string | null {
  if (!form.name.trim()) return "El nombre es obligatorio.";
  if (Boolean(form.document_type) !== Boolean(form.document_number.trim())) return "Completá el tipo y el número de documento juntos.";
  // Django aplica las reglas por país y los validadores de documentos.
  return null;
}

function CustomersPageContent() {
  const tenant = useTenant();
  const tenantId = tenant.id;
  const writable = canManage(tenant.role);

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [status, setStatus] = useState<
    "all" | "active" | "inactive"
  >("active");
  const [page, setPage] = useState(1);

  const [showForm, setShowForm] = useState(false);
  const [editingCustomer, setEditingCustomer] =
    useState<Customer | null>(null);
  const [form, setForm] = useState<CustomerFormData>(
    newCustomerForm(),
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const [countries, setCountries] = useState<ReferenceOption[]>([]);
  const [subdivisions, setSubdivisions] = useState<ReferenceOption[]>([]);
  const [geoLoading, setGeoLoading] = useState(true);
  const [geoError, setGeoError] = useState("");
  const [geoRetry, setGeoRetry] = useState(0);

  useEffect(() => {
    if (!showForm) return;
    let active = true;
    async function load() {
      setGeoLoading(true);
      setGeoError("");
      try {
        const [countriesResponse, subdivisionsResponse] = await Promise.all([
          referenceApi.countries(), referenceApi.subdivisions(form.country_code),
        ]);
        if (!active) return;
        setCountries(countriesResponse.results);
        setSubdivisions(subdivisionsResponse.results);
      } catch (err) {
        if (active) setGeoError(err instanceof ApiError ? err.message : "No se pudo cargar el catálogo geográfico.");
      } finally { if (active) setGeoLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [showForm, form.country_code, geoRetry]);

  const [busyCustomerId, setBusyCustomerId] = useState<
    string | null
  >(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCustomers() {
      setLoading(true);
      setError("");

      const filters: CustomerFilters = { page };

      if (appliedSearch.trim()) {
        filters.search = appliedSearch.trim();
      }

      if (status !== "all") {
        filters.is_active = status === "active";
      }

      try {
        const response = await customerApi.list(
          tenantId,
          filters,
        );

        if (cancelled) return;

        setCustomers(response.results);
        setCount(response.count);
        setHasNext(Boolean(response.next));
        setHasPrevious(Boolean(response.previous));
      } catch (err: unknown) {
        if (cancelled) return;

        if (err instanceof ApiError && err.status === 401) {
          redirectToLogin();
          return;
        }

        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudieron cargar los clientes.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadCustomers();

    return () => {
      cancelled = true;
    };
  }, [
    tenantId,
    appliedSearch,
    status,
    page,
    refreshKey,
  ]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedSearch(search.trim());
  }

  function openCreateForm() {
    setEditingCustomer(null);
    setForm(newCustomerForm());
    setFormError("");
    setShowForm(true);
  }

  function openEditForm(customer: Customer) {
    setEditingCustomer(customer);

    setForm({
      customer_type: customer.customer_type,
      name: customer.name,
      legal_name: customer.legal_name || "",
      document_type: customer.document_type,
      document_number: customer.document_number || "",
      email: customer.email || "",
      phone: customer.phone || "",
      address: customer.address || "",
      city: customer.city || "",
      province: customer.province || "",
      postal_code: customer.postal_code || "",
      country_code: customer.country_code || "AR",
      notes: customer.notes || "",
    });

    setFormError("");
    setShowForm(true);
  }

  function updateField<K extends keyof CustomerFormData>(
    field: K,
    value: CustomerFormData[K],
  ) {
    if (field === "country_code") {
      setGeoLoading(true);
      setSubdivisions([]);
      setForm(current => ({ ...current, country_code: String(value), province: "", postal_code: "", phone: "" }));
    } else setForm(current => ({ ...current, [field]: value }));
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (saving || geoLoading || geoError) return;

    setFormError("");

    const validationError = validateCustomerForm(form);

    if (validationError) {
      setFormError(validationError);
    return;
}

const documentNumber = form.document_number.trim();

    const payload: CustomerPayload = {
      customer_type: form.customer_type,
      name: form.name.trim(),
      legal_name: form.legal_name.trim(),
      document_type: form.document_type,
      document_number: documentNumber || null,
      email: form.email.trim(),
      phone: form.phone.trim(),
      address: form.address.trim(),
      city: form.city.trim(),
      province: form.province.trim(),
      postal_code: form.postal_code.trim(),
      country_code:
        form.country_code.trim().toUpperCase() || "AR",
      notes: form.notes.trim(),
    };

    setSaving(true);

    try {
      if (editingCustomer) {
        await customerApi.update(
          tenantId,
          editingCustomer.id,
          Object.fromEntries(Object.entries(payload).filter(([key, value]) => editingCustomer[key as keyof Customer] !== value)) as Partial<CustomerPayload>,
        );
      } else {
        await customerApi.create(tenantId, payload);
      }

      setShowForm(false);
      setEditingCustomer(null);
      setPage(1);
    setRefreshKey((current) => current + 1);
    } catch (err: unknown) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : "No se pudo guardar el cliente.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(customer: Customer) {
    const confirmed = window.confirm(
      `¿Desactivar a "${customer.name}"? Se conservará su historial.`,
    );

    if (!confirmed) return;

    setBusyCustomerId(customer.id);
    setError("");

    try {
      await customerApi.deactivate(tenantId, customer.id);
      setPage(1);
    setRefreshKey((current) => current + 1);
    } catch (err: unknown) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo desactivar el cliente.",
      );
    } finally {
      setBusyCustomerId(null);
    }
  }

  async function handleReactivate(customer: Customer) {
    setBusyCustomerId(customer.id);
    setError("");

    try {
      await customerApi.update(tenantId, customer.id, {
        is_active: true,
      });

      setPage(1);
    setRefreshKey((current) => current + 1);
    } catch (err: unknown) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo reactivar el cliente.",
      );
    } finally {
      setBusyCustomerId(null);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <Link
            href={`/dashboard/${tenantId}`}
            className="flex items-center gap-2 text-sm font-medium text-slate-600 transition hover:text-indigo-600"
          >
            <ArrowLeft size={17} />
            Espacio de trabajo
          </Link>

          <span className="flex items-center gap-2 text-sm text-slate-500">
            <Building2 size={17} />
            Gestión de clientes
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <p className="text-xs font-semibold tracking-widest text-indigo-600">
              GESTIÓN EMPRESARIAL
            </p>

            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              Clientes
            </h1>

            <p className="mt-2 text-sm text-slate-500">
              Administrá tus clientes y sus datos de contacto.
            </p>
          </div>

          <button
            disabled={!writable}
            onClick={openCreateForm}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-4 focus:ring-indigo-200"
          >
            <Plus size={18} />
            Nuevo cliente
          </button>
        </div>

        <section className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
            <form
              onSubmit={handleSearch}
              className="flex w-full gap-2 lg:max-w-xl"
            >
              <div className="relative min-w-0 flex-1">
                <Search
                  size={18}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
                />

                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Buscar por nombre, documento o correo..."
                  aria-label="Buscar clientes"
                  className={`${inputClass} mt-0 py-3 pl-10`}
                />
              </div>

              <button
                type="submit"
                className="rounded-xl border border-slate-200 px-4 text-sm font-medium transition hover:bg-slate-50"
              >
                Buscar
              </button>
            </form>

            <select
              value={status}
              onChange={(event) => {
                setStatus(
                  event.target.value as
                    | "all"
                    | "active"
                    | "inactive",
                );
                setPage(1);
              }}
              aria-label="Filtrar por estado"
              className={`${inputClass} mt-0 w-full py-3 sm:w-48`}
            >
              <option value="active">Clientes activos</option>
              <option value="inactive">Clientes inactivos</option>
              <option value="all">Todos los clientes</option>
            </select>
          </div>

          {error && (
            <div
              role="alert"
              className="m-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
            >
              <p>{error}</p>

              <button
                onClick={() => setRefreshKey((value) => value + 1)}
                className="mt-2 font-semibold underline"
              >
                Intentar nuevamente
              </button>
            </div>
          )}

          {loading ? (
            <div
              className="flex min-h-64 items-center justify-center gap-3 text-sm text-slate-500"
              role="status"
            >
              <LoaderCircle
                size={22}
                className="animate-spin text-indigo-600"
              />
              Cargando clientes...
            </div>
          ) : customers.length === 0 ? (
            <div className="flex min-h-64 flex-col items-center justify-center px-6 text-center">
              <span className="flex size-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                <UserRound size={26} />
              </span>

              <h2 className="mt-4 font-semibold">
                {appliedSearch
                  ? "No encontramos resultados"
                  : "Todavía no hay clientes"}
              </h2>

              <p className="mt-2 max-w-md text-sm text-slate-500">
                {appliedSearch
                  ? "Probá con otro nombre, documento o correo electrónico."
                  : status === "inactive"
                    ? "No hay clientes inactivos para mostrar."
                    : "Cuando agregues clientes, aparecerán en este listado."}
              </p>

              {!appliedSearch && status !== "inactive" && writable && (
                <button
                  disabled={!writable}
            onClick={openCreateForm}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
                >
                  <Plus size={17} />
                  Crear primer cliente
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-left">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-5 py-4 font-medium">
                        Cliente
                      </th>
                      <th className="px-5 py-4 font-medium">
                        Documento
                      </th>
                      <th className="px-5 py-4 font-medium">
                        Contacto
                      </th>
                      <th className="px-5 py-4 font-medium">
                        Estado
                      </th>
                      <th className="px-5 py-4 text-right font-medium">
                        Acciones
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-100">
                    {customers.map((customer) => (
                      <tr
                        key={customer.id}
                        className="transition hover:bg-slate-50/80"
                      >
                        <td className="px-5 py-4">
                          <p className="font-medium text-slate-900">
                            {customer.name}
                          </p>

                          {customer.legal_name && (
                            <p className="mt-1 text-xs text-slate-500">
                              {customer.legal_name}
                            </p>
                          )}

                          <p className="mt-1 text-xs text-slate-500">
                            {customer.customer_type === "company"
                              ? "Empresa"
                              : "Persona física"}
                          </p>
                        </td>

                        <td className="px-5 py-4 text-sm text-slate-600">
                          {customer.document_number ? (
                            <>
                              <span className="font-medium uppercase">
                                {customer.document_type}
                              </span>{" "}
                              {customer.document_number}
                            </>
                          ) : (
                            <span className="text-slate-500">
                              Sin documento
                            </span>
                          )}
                        </td>

                        <td className="px-5 py-4">
                          <p className="text-sm text-slate-700">
                            {customer.email || "Sin correo"}
                          </p>

                          <p className="mt-1 text-xs text-slate-500">
                            {customer.phone || "Sin teléfono"}
                          </p>
                        </td>

                        <td className="px-5 py-4">
                          <span
                            className={
                              customer.is_active
                                ? "inline-flex rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
                                : "inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600"
                            }
                          >
                            {customer.is_active
                              ? "Activo"
                              : "Inactivo"}
                          </span>
                        </td>

                        <td className="px-5 py-4">
                          <div className="flex justify-end gap-2">
                            <button
                              disabled={!writable}
                              onClick={() => openEditForm(customer)}
                              title="Editar cliente"
                              aria-label={`Editar ${customer.name}`}
                              className="rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600"
                            >
                              <Pencil size={16} />
                            </button>

                            {customer.is_active ? (
                              <button
                                onClick={() =>
                                  void handleDeactivate(customer)
                                }
                                disabled={
                                  !writable || busyCustomerId === customer.id
                                }
                                title="Desactivar cliente"
                                aria-label={`Desactivar ${customer.name}`}
                                className="rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                              >
                                {busyCustomerId === customer.id ? (
                                  <LoaderCircle
                                    size={16}
                                    className="animate-spin"
                                  />
                                ) : (
                                  <UserX size={16} />
                                )}
                              </button>
                            ) : (
                              <button
                                onClick={() =>
                                  void handleReactivate(customer)
                                }
                                disabled={
                                  !writable || busyCustomerId === customer.id
                                }
                                title="Reactivar cliente"
                                className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 disabled:opacity-50"
                              >
                                {busyCustomerId === customer.id
                                  ? "..."
                                  : "Reactivar"}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-500">
                  {count} {count === 1 ? "cliente" : "clientes"}
                </p>

                <div className="flex items-center justify-end gap-2">
                  <span className="mr-2 text-sm text-slate-500">
                    Página {page}
                  </span>

                  <button
                    onClick={() =>
                      setPage((current) => Math.max(1, current - 1))
                    }
                    disabled={!hasPrevious || loading}
                    aria-label="Página anterior"
                    className="rounded-lg border border-slate-200 p-2 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft size={18} />
                  </button>

                  <button
                    onClick={() => setPage((current) => current + 1)}
                    disabled={!hasNext || loading}
                    aria-label="Página siguiente"
                    className="rounded-lg border border-slate-200 p-2 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronRight size={18} />
                  </button>
                </div>
              </div>
            </>
          )}
        </section>

        <p className="mt-4 text-xs text-slate-500">
          Los clientes pertenecen a esta empresa. Su historial se conserva
          cuando se desactivan.
        </p>
      </div>

      {showForm && (
        <Modal title={editingCustomer ? "Editar cliente" : "Nuevo cliente"} busy={saving} onClose={() => setShowForm(false)}>
            <form onSubmit={handleSave} className="p-5 sm:p-7">
              <p className="mb-4 text-xs text-slate-500">Los documentos, teléfonos y domicilios se revisan por formato; no se verifica su existencia ni titularidad.</p>
              {formError && (
                <div
                  role="alert"
                  className="mb-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
                >
                  {formError}
                </div>
              )}

              {geoError && <div role="alert" className="notice-error">{geoError}<button type="button" className="button secondary" onClick={() => setGeoRetry(value => value + 1)}>Reintentar catálogo</button></div>}
              <fieldset disabled={saving} className="grid gap-5 sm:grid-cols-2">
                <label className={labelClass}>
                  Tipo de cliente *
                  <select
                    required
                    value={form.customer_type}
                    onChange={(event) =>
                      updateField(
                        "customer_type",
                        event.target.value as CustomerType,
                      )
                    }
                    className={inputClass}
                  >
                    <option value="individual">Persona física</option>
                    <option value="company">Empresa</option>
                  </select>
                </label>

                <label className={labelClass}>
                  Nombre o denominación *
                  <input
                    required
                    maxLength={150}
                    value={form.name}
                    onChange={(event) =>
                      updateField("name", event.target.value)
                    }
                    className={inputClass}
                    placeholder="Nombre del cliente"
                  />
                </label>

                <label className={labelClass}>
                  Razón social
                  <input
                    maxLength={200}
                    value={form.legal_name}
                    onChange={(event) =>
                      updateField("legal_name", event.target.value)
                    }
                    className={inputClass}
                    placeholder="Opcional"
                  />
                </label>

                <label className={labelClass}>
                  Tipo de documento
                  <select
                    value={form.document_type}
                    onChange={(event) =>
                      updateField(
                        "document_type",
                        event.target.value as CustomerDocumentType,
                      )
                    }
                    className={inputClass}
                  >
                    <option value="">Sin documento</option>
                    <option value="dni">DNI</option>
                    <option value="cuit">CUIT</option>
                    <option value="cuil">CUIL</option>
                    <option value="other">Otro</option>
                  </select>
                </label>

                <label className={labelClass}>
                  Número de documento
                  <input
                    maxLength={30}
                    value={form.document_number}
                    onChange={(event) =>
                      updateField(
                        "document_number",
                        event.target.value,
                      )
                    }
                    className={inputClass}
                    placeholder="Número de documento"
                  />
                </label>

                <label className={labelClass}>
                  Correo electrónico
                  <input
                    type="email"
                    maxLength={254}
                    value={form.email}
                    onChange={(event) =>
                      updateField("email", event.target.value)
                    }
                    className={inputClass}
                    placeholder="cliente@ejemplo.com"
                  />
                </label>

                <label className={labelClass}>
                  Teléfono
                  <input
                    type="tel"
                    maxLength={32}
                    value={form.phone}
                    onChange={(event) =>
                      updateField("phone", event.target.value)
                    }
                    className={inputClass}
                    placeholder="Código de área o formato +54…"
                  />
                </label>

                <label className={labelClass}>
                  País *
                  <select required aria-label="País" value={form.country_code} onChange={event => updateField("country_code", event.target.value)} disabled={geoLoading || !!geoError} className={inputClass}>
                    {countries.length ? countries.map(country => <option key={country.code} value={country.code}>{country.name} ({country.code})</option>) : <option value={form.country_code}>Cargando países…</option>}
                  </select>
                  <span className="mt-1 block text-xs font-normal text-slate-500">Cambiar el país limpia provincia, código postal y teléfono.</span>
                </label>

                <label className={labelClass}>
                  Dirección
                  <input
                    maxLength={255}
                    value={form.address}
                    onChange={(event) =>
                      updateField("address", event.target.value)
                    }
                    className={inputClass}
                    placeholder="Calle y número"
                  />
                </label>

                <label className={labelClass}>
                  Ciudad
                  <input
                    maxLength={120}
                    value={form.city}
                    onChange={(event) =>
                      updateField("city", event.target.value)
                    }
                    className={inputClass}
                  />
                </label>

                <label className={labelClass}>
                  Provincia / estado
                  <select aria-label="Provincia / estado" value={form.province} disabled={geoLoading || !!geoError} onChange={event => updateField("province", event.target.value)} className={inputClass}>
                    <option value="">{geoLoading ? "Cargando subdivisiones…" : subdivisions.length ? "Sin especificar" : "Sin subdivisiones en el catálogo"}</option>
                    {form.province && !subdivisions.some(item => item.name === form.province) && <option value={form.province}>{form.province} (registro anterior)</option>}
                    {subdivisions.map(item => <option key={item.code} value={item.name}>{item.name}</option>)}
                  </select>
                </label>

                <label className={labelClass}>
                  Código postal (AR: CPA o cuatro dígitos)
                  <input
                    maxLength={20}
                    value={form.postal_code}
                    onChange={(event) =>
                      updateField("postal_code", event.target.value)
                    }
                    className={inputClass}
                  />
                </label>

                <label className={`${labelClass} sm:col-span-2`}>
                  Notas internas
                  <textarea
                    rows={3}
                    value={form.notes}
                    onChange={(event) =>
                      updateField("notes", event.target.value)
                    }
                    className={inputClass}
                    placeholder="Información adicional opcional"
                  />
                </label>
              </fieldset>

              <footer className="mt-7 flex flex-col-reverse justify-end gap-3 border-t border-slate-100 pt-5 sm:flex-row">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => setShowForm(false)}
                  className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-medium transition hover:bg-slate-50"
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  disabled={saving || geoLoading || !!geoError}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving && (
                    <LoaderCircle
                      size={17}
                      className="animate-spin"
                    />
                  )}
                  {saving
                    ? "Guardando..."
                    : editingCustomer
                      ? "Guardar cambios"
                      : "Crear cliente"}
                </button>
              </footer>
            </form>
        </Modal>
      )}
    </main>
  );
}

export default function CustomersPage() {
  return (
    <Suspense
      fallback={
        <main className="dashboard-loading">
          <LoaderCircle size={26} className="animate-spin" />
          <p>Cargando clientes...</p>
        </main>
      }
    >
      <CustomersPageContent />
    </Suspense>
  );
}
