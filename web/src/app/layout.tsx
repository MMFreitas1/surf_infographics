import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ErrorReporter } from "./error-reporter";
import "./globals.css";

export const metadata: Metadata = {
  title: "Surf Infographics",
  description: "Local-first surf session analytics",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ErrorReporter />
        {children}
      </body>
    </html>
  );
}
