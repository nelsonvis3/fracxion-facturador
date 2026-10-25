import type { Metadata } from "next";
import { Public_Sans } from "next/font/google";
import "./globals.css";
import { SessionTransitionProvider } from "@/components/session-transition";

// Tipografía de formularios oficiales con cifras tabulares: los montos quedan alineados como en una planilla.
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-libro", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Fracxion · Gestión empresarial", template: "%s · Fracxion" },
  description: "Clientes, catálogo, facturación interna y cobros con acceso por empresa.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es-AR"
      className={`${publicSans.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col"><SessionTransitionProvider>{children}</SessionTransitionProvider></body>
    </html>
  );
}
