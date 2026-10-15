import type { Invoice } from "./business-api";
export const receivableLabels: Record<Invoice["receivable_status"], string> = { draft: "Borrador", paid: "Pagada", unscheduled: "Sin vencimiento informado", overdue: "Vencida", due_today: "Vence hoy", upcoming: "Por vencer" };
export const displayDate = (value: string | null) => value ? new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`)) : "Sin vencimiento informado";
