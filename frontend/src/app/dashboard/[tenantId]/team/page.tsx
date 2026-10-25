"use client";
import { useCallback, useState, type FormEvent } from "react";
import type { Tenant } from "@/lib/api";
import { canManage, dateTime } from "@/lib/business-api";
import { enterpriseApi, roleLabels, type Member, type Invitation } from "@/lib/enterprise-api";
import { Alert, Empty, Loading, PageHeading, Pagination, errorMessage, useAsync } from "@/components/business-ui";
import { EnterpriseField, fieldErrors } from "@/components/enterprise-fields";
import { useTenant, useTenantRefresh } from "@/components/tenant-workspace";

const deliveryLabels = { pending: "Envío pendiente", sent: "Correo enviado", failed: "Falló el envío: revisá el correo o reintentá" };
const stateLabels = { pending: "Pendiente", accepted: "Aceptada", revoked: "Revocada", expired: "Vencida" };
function MemberRow({ member, onSaved }: { member: Member; onSaved: () => void }) {
  const tenant = useTenant(); const [role, setRole] = useState(member.role); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const allowed = tenant.role === "owner" || !["owner", "admin"].includes(member.role);
  const roles = (Object.keys(roleLabels) as Tenant["role"][]).filter(role => tenant.role === "owner" || !["owner", "admin"].includes(role));
  async function update(data: Partial<Pick<Member, "role" | "is_active">>) {
    if (busy || !window.confirm(`¿Confirmar el cambio de acceso de ${member.email}?`)) return;
    setBusy(true); setError("");
    try { await enterpriseApi.updateMember(tenant.id, member.id, data); onSaved(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <tr><td><strong>{[member.first_name, member.last_name].filter(Boolean).join(" ") || member.email}</strong><small>{member.email}</small>{error && <div className="mt-2" role="alert">{error}</div>}</td><td>{allowed ? <select className="input" aria-label={`Rol de ${member.email}`} value={role} disabled={busy} onChange={event => setRole(event.target.value as Tenant["role"])}>{roles.map(role => <option key={role} value={role}>{roleLabels[role]}</option>)}</select> : roleLabels[member.role]}</td><td><span className={`badge ${member.is_active && member.user_active ? "active" : "inactive"}`}>{!member.user_active ? "Cuenta desactivada" : member.is_active ? "Activa" : "Desactivada"}</span></td><td>{allowed && <div className="row-actions">{role !== member.role && <button className="button secondary" disabled={busy} onClick={() => void update({ role })}>Guardar rol</button>}<button className="button secondary" disabled={busy || !member.user_active} onClick={() => void update({ is_active: !member.is_active })}>{member.is_active ? "Desactivar" : "Activar"}</button></div>}</td></tr>;
}
function InvitationRow({ invitation, onSaved }: { invitation: Invitation; onSaved: () => void }) {
  const tenant = useTenant(); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const allowed = ["pending", "expired"].includes(invitation.state) && (tenant.role === "owner" || !["owner", "admin"].includes(invitation.role));
  async function manage(action: "resend" | "revoke") {
    if (busy || !window.confirm(action === "resend" ? "¿Reenviar esta invitación? El enlace anterior dejará de funcionar." : "¿Revocar esta invitación?")) return;
    setBusy(true); setError("");
    try { await enterpriseApi.manageInvitation(tenant.id, invitation.id, action); onSaved(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <tr><td>{invitation.email}<small>{deliveryLabels[invitation.delivery_status]}</small>{error && <p role="alert">{error}</p>}</td><td>{roleLabels[invitation.role]}</td><td>{stateLabels[invitation.state]}<small>Vence {dateTime(invitation.expires_at)}</small></td><td>{allowed && <div className="row-actions"><button className="button secondary" disabled={busy} onClick={() => void manage("resend")}>Reenviar</button><button className="button secondary" disabled={busy} onClick={() => void manage("revoke")}>Revocar</button></div>}</td></tr>;
}

export default function TeamPage() {
  const refreshTenant = useTenantRefresh();
  const tenant = useTenant(); const [page, setPage] = useState(1); const [invitationPage, setInvitationPage] = useState(1);
  const [email, setEmail] = useState(""); const [role, setRole] = useState<Tenant["role"]>("viewer"); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [errors, setErrors] = useState<Record<string, string>>({}); const [sent, setSent] = useState(false);
  const state = useAsync(useCallback(async () => canManage(tenant.role) ? Promise.all([enterpriseApi.members(tenant.id, page), enterpriseApi.invitations(tenant.id, invitationPage)]) : null, [tenant.id, tenant.role, page, invitationPage]));
  if (!canManage(tenant.role)) return <main className="module-content"><Alert>Solo propietarios y administradores pueden administrar el equipo.</Alert></main>;
  async function invite(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    if (["owner", "admin"].includes(role) && !window.confirm(`¿Invitar a ${email} como ${roleLabels[role]}?`)) return;
    setBusy(true); setError(""); setErrors({}); setSent(false);
    try { await enterpriseApi.invite(tenant.id, email, role); setEmail(""); setRole("viewer"); setSent(true); state.refresh(); }
    catch (err) { setError(errorMessage(err)); setErrors(fieldErrors(err)); }
    finally { setBusy(false); }
  }
  const roles = (Object.keys(roleLabels) as Tenant["role"][]).filter(role => tenant.role === "owner" || !["owner", "admin"].includes(role));
  return <main className="module-content"><PageHeading title="Equipo e invitaciones" description="Gestioná el acceso a esta empresa. Cada cambio sensible queda en el historial." />
    <section className="panel mb-6 p-6"><h2 className="mb-4 text-lg font-semibold">Invitar a una persona</h2><p className="mb-5 text-sm text-slate-600">Recibirá un enlace de uso único que vence en siete días. Si ya tiene una cuenta, deberá iniciar sesión con ese correo.</p><form onSubmit={invite} aria-label="Invitar al equipo">{error && <Alert>{error}</Alert>}{sent && <p className="notice-info" role="status">Invitación registrada. Consultá el resultado del envío en la lista.</p>}<fieldset className="form-grid" disabled={busy}><EnterpriseField id="invite-email" label="Correo del destinatario *" error={errors.email}><input id="invite-email" className="input" type="email" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} /></EnterpriseField><EnterpriseField id="invite-role" label="Rol" error={errors.role}><select id="invite-role" className="input" value={role} onChange={event => setRole(event.target.value as Tenant["role"])}>{roles.map(role => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></EnterpriseField></fieldset><footer className="form-footer"><button className="button" disabled={busy}>{busy ? "Registrando…" : "Enviar invitación"}</button></footer></form></section>
    {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <>
      <section className="panel mb-6"><h2 className="p-6 text-lg font-semibold">Miembros de la empresa</h2><div className="table-scroll" tabIndex={0} role="region" aria-label="Miembros del equipo"><table className="data-table"><thead><tr><th>Persona</th><th>Rol</th><th>Acceso</th><th>Acciones</th></tr></thead><tbody>{state.data[0].results.map(member => <MemberRow key={`${member.id}:${member.role}:${member.is_active}`} member={member} onSaved={() => { void refreshTenant().catch(() => {}).finally(state.refresh); }} />)}</tbody></table></div><Pagination data={state.data[0]} page={page} setPage={setPage} /></section>
      <section className="panel"><h2 className="p-6 text-lg font-semibold">Invitaciones</h2>{state.data[1].results.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Invitaciones del equipo"><table className="data-table"><thead><tr><th>Destinatario y entrega</th><th>Rol</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{state.data[1].results.map(invitation => <InvitationRow key={invitation.id} invitation={invitation} onSaved={state.refresh} />)}</tbody></table></div> : <Empty>No hay invitaciones. Podés invitar a una persona desde el formulario.</Empty>}<Pagination data={state.data[1]} page={invitationPage} setPage={setInvitationPage} /></section>
    </>}
  </main>;
}
