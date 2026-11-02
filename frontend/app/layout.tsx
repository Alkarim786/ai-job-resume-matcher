import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Job & Resume Matcher", description: "Explainable semantic matching for candidates and recruiters" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
