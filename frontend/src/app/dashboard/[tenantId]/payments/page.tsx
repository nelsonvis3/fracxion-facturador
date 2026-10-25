"use client";
import { useState } from "react";
import { Plus } from "lucide-react";
import { canRecordPayment } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { PageHeading } from "@/components/business-ui";
import { PaymentForm } from "@/components/payment-form";
import { PaymentHistory } from "@/components/payment-history";

export default function PaymentsPage() {
  const tenant = useTenant();
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState(0);
  return <main className="module-content"><PageHeading title="Pagos" description="Cobros, referencias y reversiones con historial conservado.">{canRecordPayment(tenant.role) && <button className="button" onClick={() => setOpen(true)}><Plus size={17} />Registrar pago</button>}</PageHeading><PaymentHistory refreshKey={version} />{open && <PaymentForm onClose={() => setOpen(false)} onSaved={() => setVersion(value => value + 1)} />}</main>;
}
