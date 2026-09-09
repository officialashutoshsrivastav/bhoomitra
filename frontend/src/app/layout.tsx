import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { BootLoader, RouteProgress } from "@/components/Loader";

/* Fonts are linked rather than fetched by `next/font`, so `next build` works on
   a machine with no route to Google — which matters for a firewalled government
   deployment. To remove the runtime dependency entirely, drop the .woff2 files
   into /public/fonts and swap these links for @font-face in globals.css.

   Inter was named in the Tailwind config before but never actually loaded, so
   every page was silently falling back to the system UI font. */

export const metadata: Metadata = {
  title: { default: "Bhoomitra — Land Governance Intelligence Platform", template: "%s · Bhoomitra" },
  description: "National digital platform for research, policy innovation and evidence-based land governance. Department of Land Resources, Ministry of Rural Development.",
  icons: { icon: "/logo.jpeg" },
};

export const viewport: Viewport = {
  themeColor: "#0f5f3a",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- that rule targets
            the Pages Router; in the App Router this <head> is global to every route. */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap"
        />
      </head>
      <body className="font-sans">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
        >
          Skip to content
        </a>
        <BootLoader />
        <RouteProgress />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
