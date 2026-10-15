"use client";
import { cloneElement, type ReactElement } from "react";
import { ApiError } from "@/lib/api";

export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.body || typeof error.body !== "object") return {};
  return Object.fromEntries(Object.entries(error.body).filter(([key]) => !["detail", "non_field_errors"].includes(key)).map(([key, value]) => [key, Array.isArray(value) ? value.join(" ") : typeof value === "string" ? value : "Revisá este campo."]));
}
export function EnterpriseField({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactElement<{ "aria-invalid"?: boolean; "aria-describedby"?: string }> }) {
  const describedBy = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return <div className="field"><label htmlFor={id}>{label}</label>{cloneElement(children, { "aria-invalid": !!error, "aria-describedby": describedBy })}{hint && <small id={`${id}-hint`} className="font-normal text-slate-600">{hint}</small>}{error && <p id={`${id}-error`} className="text-sm font-normal text-red-700" role="alert">{error}</p>}</div>;
}
