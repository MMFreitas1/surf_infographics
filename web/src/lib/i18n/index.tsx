"use client";

/**
 * Locale resolution and message lookup.
 *
 * A local-first app has no account to carry a preference, so the locale comes from the
 * browser (`navigator.language`) with an explicit override kept in `localStorage`. That is
 * the whole mechanism — there is no server to negotiate with.
 *
 * Resolution runs in an effect rather than during render on purpose. `navigator` does not
 * exist while Next renders on the server, and reading it during the first client render
 * would make the markup disagree with the server's and trip hydration. So the first paint is
 * the default locale and the resolved one lands immediately after.
 */
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { DEFAULT_LOCALE, LOCALES, type LocaleTag, type Messages } from "./catalog";
import { en } from "./en";
import { ptPT } from "./pt-PT";

const CATALOGUES: Record<LocaleTag, Messages> = { "pt-PT": ptPT, en };

const OVERRIDE_KEY = "surf.locale";

/** The catalogue locale that best matches a browser tag, or null when none does. */
export function matchLocale(tag: string | undefined): LocaleTag | null {
  if (!tag) return null;
  const lower = tag.toLowerCase();
  const exact = LOCALES.find((l) => l.toLowerCase() === lower);
  if (exact) return exact;
  // "pt", "pt-BR" and "pt-PT" all get the Portuguese catalogue: a rough match in the right
  // language beats an exact match in the wrong one.
  const base = lower.split("-")[0];
  return LOCALES.find((l) => l.toLowerCase().split("-")[0] === base) ?? null;
}

/** What the browser asks for, honouring an explicit override first. */
export function resolveLocale(): LocaleTag {
  try {
    const override = window.localStorage.getItem(OVERRIDE_KEY);
    const chosen = matchLocale(override ?? undefined);
    if (chosen) return chosen;
  } catch {
    // Private browsing, or storage blocked. Fall through to the browser's own preference.
  }
  for (const tag of navigator.languages ?? [navigator.language]) {
    const matched = matchLocale(tag);
    if (matched) return matched;
  }
  return DEFAULT_LOCALE;
}

interface LocaleValue {
  locale: LocaleTag;
  messages: Messages;
  setLocale: (locale: LocaleTag) => void;
}

const LocaleContext = createContext<LocaleValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleTag>(DEFAULT_LOCALE);

  useEffect(() => {
    setLocaleState(resolveLocale());
  }, []);

  const value = useMemo<LocaleValue>(
    () => ({
      locale,
      messages: CATALOGUES[locale],
      setLocale: (next) => {
        setLocaleState(next);
        try {
          window.localStorage.setItem(OVERRIDE_KEY, next);
        } catch {
          // An override that cannot be remembered still applies to this visit.
        }
      },
    }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleValue {
  const value = useContext(LocaleContext);
  if (value === null) {
    throw new Error("useLocale outside a LocaleProvider: the whole app must sit inside one");
  }
  return value;
}

/**
 * Message lookup with `{name}` interpolation.
 *
 * Interpolation is positional-free and deliberately dumb: a catalogue is data, and anything
 * cleverer here becomes a templating language nobody asked for. Numbers arriving through
 * `values` should already have been through `Intl` — see `lib/format.ts`.
 */
export function useT(): (key: keyof Messages, values?: Record<string, string | number>) => string {
  const { messages } = useLocale();
  return (key, values) => {
    const template = messages[key];
    if (!values) return template;
    return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
      name in values ? String(values[name]) : whole,
    );
  };
}
