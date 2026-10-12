import { Suspense, type ReactNode } from "react";
import { TenantWorkspace } from "@/components/tenant-workspace";
import { Loading } from "@/components/business-ui";

export default function TenantLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Loading />}><TenantWorkspace>{children}</TenantWorkspace></Suspense>;
}
