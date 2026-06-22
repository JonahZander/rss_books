import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { ToastProvider } from "../components/Toasts";
import "./globals.css";

// Fonts are self-hosted (variable woff2 in ./fonts) rather than fetched from
// Google Fonts at build time — keeps the Docker build hermetic and offline.
// The weight ranges mirror the original next/font/google declarations.
const archivo = localFont({
  src: "./fonts/archivo.woff2",
  weight: "500 900",
  variable: "--font-archivo",
  display: "swap",
});

const plex = localFont({
  src: "./fonts/ibm-plex-sans.woff2",
  weight: "300 500",
  variable: "--font-plex",
  display: "swap",
});

const jetbrains = localFont({
  src: "./fonts/jetbrains-mono.woff2",
  weight: "400 500",
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RSS / Kindle Selector",
  description:
    "The self-hosted news desk for your e-reader. Pick your news, press an edition, read it anywhere.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${archivo.variable} ${plex.variable} ${jetbrains.variable}`}>
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
