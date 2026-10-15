"use client";
import { useCallback, useState, type FormEvent } from "react";
import Image from "next/image";
import { canManage } from "@/lib/business-api";
import { enterpriseApi, type BusinessSettings } from "@/lib/enterprise-api";
import { useTenant, useTenantRefresh } from "@/components/tenant-workspace";
import { Alert, Loading, PageHeading, errorMessage, useAsync } from "@/components/business-ui";
import { EnterpriseField, fieldErrors } from "@/components/enterprise-fields";

function SettingsForm({ initial }: { initial: BusinessSettings }) {
  const tenant = useTenant();
  const refreshTenant = useTenantRefresh();
  const [data, setData] = useState(initial);
  const [logo, setLogo] = useState<string>();
  const [removeLogo, setRemoveLogo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingLogo, setLoadingLogo] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const editable = canManage(tenant.role);
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy || loadingLogo || !editable) return;
    setBusy(true); setError(""); setErrors({}); setSaved(false);
    try {
      const result = await enterpriseApi.updateSettings(tenant.id, { ...data, ...(logo ? { logo_data: logo } : {}), ...(removeLogo ? { remove_logo: true } : {}) });
      setData(result); setLogo(undefined); setRemoveLogo(false); setSaved(true);
      try { await refreshTenant(); } catch { setError("La configuración quedó guardada. Recargá la página para actualizar los datos de navegación."); }
    } catch (err) { setError(errorMessage(err)); setErrors(fieldErrors(err)); }
    finally { setBusy(false); }
  }
  const descriptors: { key: keyof BusinessSettings; label: string; type?: string; max?: number; hint?: string }[] = [
    { key: "name", label: "Nombre visible *", max: 150 }, { key: "legal_name", label: "Nombre legal", max: 200 },
    { key: "tax_id", label: "Identificación tributaria", max: 20 }, { key: "country_code", label: "País ISO *", max: 2, hint: "Código de dos letras, por ejemplo AR." },
    { key: "timezone", label: "Zona horaria *", max: 64, hint: "Por ejemplo America/Argentina/Cordoba o UTC." }, { key: "default_currency", label: "Moneda predeterminada *", max: 3, hint: "Código ISO, por ejemplo ARS. No convierte importes existentes." },
    { key: "contact_email", label: "Correo de contacto", type: "email" }, { key: "contact_phone", label: "Teléfono de contacto", type: "tel", max: 40 },
    { key: "address", label: "Dirección comercial", max: 255 }, { key: "website", label: "Sitio web", type: "url" },
  ];
  return <form onSubmit={save} aria-label="Configuración empresarial">
    {error && <Alert>{error}</Alert>}{saved && <p className="notice-info" role="status">La configuración quedó guardada. Los comprobantes existentes conservan sus datos.</p>}
    {!editable && <p className="notice-info">Podés consultar la configuración. Solo propietarios y administradores pueden modificarla.</p>}
    <fieldset disabled={busy || !editable} className="grid gap-6">
      <section className="panel p-6"><h2 className="mb-5 text-lg font-semibold">Información comercial</h2><div className="form-grid">{descriptors.map(field => {
        const id = `settings-${field.key}`; return <EnterpriseField key={field.key} id={id} label={field.label} error={errors[field.key]} hint={field.hint}><input id={id} className="input" type={field.type ?? "text"} maxLength={field.max} required={field.label.endsWith("*")} aria-invalid={!!errors[field.key]} aria-describedby={errors[field.key] ? `${id}-error` : field.hint ? `${id}-hint` : undefined} value={String(data[field.key] ?? "")} onChange={event => { setSaved(false); setData({ ...data, [field.key]: ["country_code", "default_currency"].includes(field.key) ? event.target.value.toUpperCase() : event.target.value }); }} /></EnterpriseField>;
      })}</div></section>
      <section className="panel p-6"><h2 className="mb-5 text-lg font-semibold">Preferencias de comprobantes</h2><div className="form-grid"><EnterpriseField id="settings-terms" label="Plazo predeterminado de pago (días)" error={errors.payment_terms_days} hint="Vacío significa sin vencimiento predeterminado. Para nuevos borradores, el plazo se cuenta desde el día de creación en la zona de la empresa."><input id="settings-terms" className="input" type="number" min={0} max={3650} step={1} value={data.payment_terms_days ?? ""} onChange={event => setData({ ...data, payment_terms_days: event.target.value === "" ? null : Number(event.target.value) })} /></EnterpriseField><EnterpriseField id="settings-footer" label="Pie del comprobante" error={errors.invoice_footer} hint="Se conserva como texto histórico al crear nuevos documentos."><textarea id="settings-footer" className="input" rows={3} maxLength={1000} value={data.invoice_footer} onChange={event => setData({ ...data, invoice_footer: event.target.value })} /></EnterpriseField></div><label className="mt-5 flex items-center gap-3 text-sm"><input type="checkbox" checked={data.payment_reminders_enabled} onChange={event => setData({ ...data, payment_reminders_enabled: event.target.checked })} />Permitir recordatorios de vencimiento configurados para esta empresa</label></section>
      <section className="panel p-6"><h2 className="mb-3 text-lg font-semibold">Logo empresarial</h2>{(logo || data.has_logo) && !removeLogo && <Image className="mb-4 rounded-lg border object-contain p-2" src={logo ? `data:image/png;base64,${logo}` : enterpriseApi.logoUrl(tenant.id, data.logo_updated_at)} width={128} height={128} unoptimized alt={`Logo de ${data.name}`} />}<EnterpriseField id="settings-logo" label="Subir logo PNG o JPEG" hint="Hasta 512 KB y 2048 px por lado. Se procesa y almacena de forma privada."><input id="settings-logo" type="file" accept="image/png,image/jpeg" className="input" onChange={event => {
        const file = event.target.files?.[0]; if (!file) return;
        if (file.size > 512 * 1024 || !["image/png", "image/jpeg"].includes(file.type)) { setError("Elegí una imagen PNG o JPEG de hasta 512 KB."); event.target.value = ""; return; }
        setLoadingLogo(true);
        const reader = new FileReader(); reader.onerror = () => { setError("No se pudo leer la imagen."); setLoadingLogo(false); }; reader.onload = () => { setLogo(String(reader.result).split(",")[1]); setRemoveLogo(false); setError(""); setLoadingLogo(false); }; reader.readAsDataURL(file);
      }} /></EnterpriseField>{data.has_logo && <label className="mt-4 flex items-center gap-3 text-sm"><input type="checkbox" checked={removeLogo} onChange={event => { setRemoveLogo(event.target.checked); setLogo(undefined); }} />Quitar el logo al guardar</label>}</section>
    </fieldset>
    {editable && <footer className="form-footer"><button className="button" disabled={busy || loadingLogo}>{loadingLogo ? "Leyendo imagen…" : busy ? "Guardando…" : "Guardar configuración"}</button></footer>}
  </form>;
}

export default function SettingsPage() {
  const tenant = useTenant(); const state = useAsync(useCallback(() => enterpriseApi.settings(tenant.id), [tenant.id]));
  return <main className="module-content"><PageHeading title="Configuración de empresa" description="Información comercial y preferencias que se aplican a las próximas operaciones." />{state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <SettingsForm initial={state.data} />}</main>;
}
