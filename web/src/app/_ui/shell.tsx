"use client";

/**
 * The frame every level sits in: masthead, tab bar, section headers, footer.
 *
 * Shared because the design's three levels differ in their body and not their chrome, and
 * because the gradient rule under the masthead is the only gradient bar in the product —
 * one component owning it is how that stays true.
 *
 * This is a desktop tool. The design sets a 1440px minimum deliberately and it is not
 * responsive below that; a session map and four chart cards side by side do not survive a
 * phone, and pretending otherwise would mean designing a second product.
 */
import Image from "next/image";
import Link from "next/link";
import { type ReactNode, useEffect } from "react";
import { useLocale, useT } from "@/lib/i18n";
import type { Messages } from "@/lib/i18n/catalog";

/** Corrects `<html lang>` once the locale is known. See the note in `layout.tsx`. */
function LocaleHtmlLang() {
  const { locale } = useLocale();
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return null;
}

export type Level = "sessions" | "session" | "wave";

const TABS: { level: Level; key: keyof Messages; href: string }[] = [
  { level: "sessions", key: "tab.sessions", href: "/" },
  { level: "session", key: "tab.session", href: "" },
  { level: "wave", key: "tab.wave", href: "" },
];

function Masthead({ spot }: { spot: string }) {
  const t = useT();
  return (
    <header className="masthead">
      {/* Decorative: the wordmark beside it already names the product, so an alt here
          would only make a screen reader say it twice. The source is 1024px square and
          next/image resizes it -- shipping a megabyte for a 34px mark would be silly. */}
      <Image
        src="/logo-mark.png"
        alt=""
        width={34}
        height={34}
        className="masthead-mark"
        priority
      />
      <div>
        <p className="eyebrow">{t("app.eyebrow")}</p>
        <h1 className="masthead-title">{t("app.title")}</h1>
      </div>
      <p className="masthead-provenance">{t("app.provenance", { spot })}</p>
    </header>
  );
}

function TabBar({ active, sessionHref }: { active: Level; sessionHref: string | null }) {
  const t = useT();
  return (
    <nav className="tab-bar" aria-label={t("app.title")}>
      {TABS.map((tab) => {
        const href = tab.level === "sessions" ? "/" : sessionHref;
        const isActive = tab.level === active;
        // A level with nowhere to go is not a link. The wave screen does not exist yet and
        // a tab that looks clickable and is not is worse than one that says so.
        if (href === null) {
          return (
            <span key={tab.level} className="tab tab-disabled" aria-disabled="true">
              {t(tab.key)}
            </span>
          );
        }
        return (
          <Link
            key={tab.level}
            href={href}
            className={isActive ? "tab tab-active" : "tab"}
            aria-current={isActive ? "page" : undefined}
          >
            {t(tab.key)}
          </Link>
        );
      })}
    </nav>
  );
}

export function SectionHeader({ label }: { label: keyof Messages }) {
  const t = useT();
  return (
    <div className="section-header">
      <span className="section-marker" aria-hidden="true" />
      <h2 className="section-label">{t(label)}</h2>
      <span className="section-rule" aria-hidden="true" />
    </div>
  );
}

export function Shell({
  active,
  spot,
  samples,
  sessionHref = null,
  children,
}: {
  active: Level;
  spot: string;
  samples: string;
  sessionHref?: string | null;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <div className="shell">
      <LocaleHtmlLang />
      <Masthead spot={spot} />
      <div className="masthead-rule" aria-hidden="true" />
      <TabBar active={active} sessionHref={sessionHref} />
      <main>{children}</main>
      <footer className="app-footer">{t("app.footer", { spot, samples })}</footer>
    </div>
  );
}
