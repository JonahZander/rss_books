import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Jonah Base",
  description: "Personal portfolio scaffold built with Next.js, FastAPI, and agent-friendly docs.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
