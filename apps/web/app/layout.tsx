import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "RSS Kindle Selector",
  description: "Browse RSS feeds, bundle articles into a Kindle-ready digest.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
