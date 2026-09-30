import type { Metadata } from "next";
import { DM_Mono, Hanken_Grotesk, Saira } from "next/font/google";
import type { ReactNode } from "react";
import { LocaleProvider } from "@/lib/i18n";
import { ErrorReporter } from "./error-reporter";
import "./globals.css";

/**
 * The three faces the design system specifies: Saira for display, Hanken Grotesk for body,
 * DM Mono for the technical eyebrows and data labels.
 *
 * Loaded through `next/font/google` rather than the `@import` the token CSS ships with,
 * because that import fetches from `fonts.googleapis.com` at *runtime* and
 * `architecture.md` section 7 requires the app to work with no network at all. `next/font`
 * downloads at build time and self-hosts, so a session opens offline in the right typeface
 * instead of falling back silently.
 */
const saira = Saira({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});

const hanken = Hanken_Grotesk({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Surf Analytics",
  description: "Local-first surf session analytics",
};

/**
 * `lang` stays "en" here and is corrected on the client once the locale resolves.
 *
 * It cannot be right at this point: the server has no `navigator` to ask, and guessing from
 * a header would need a server this app deliberately does not have. `<LocaleHtmlLang>` in
 * the shell sets it after resolution, which is the earliest honest moment.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${saira.variable} ${hanken.variable} ${dmMono.variable}`}>
      <body>
        <ErrorReporter />
        <LocaleProvider>{children}</LocaleProvider>
      </body>
    </html>
  );
}
