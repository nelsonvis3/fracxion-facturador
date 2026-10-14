import type { Metadata } from "next";
import "./globals.css";
import { SessionTransitionProvider } from "@/components/session-transition";

export const metadata: Metadata = {
  title: { default: "Fracxion · Gestión empresarial", template: "%s · Fracxion" },
  description: "Clientes, catálogo, facturación interna y cobros con acceso por empresa.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es-AR"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col"><SessionTransitionProvider>{children}</SessionTransitionProvider></body>
    </html>
  );
}
