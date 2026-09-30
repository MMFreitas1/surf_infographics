"use client";

/**
 * Where "proposed" is said — once, for the whole session.
 *
 * This banner is the entire mechanism by which ADR-0013 is honoured on screen. The rule is
 * that no accuracy claim ships until a session is labelled the day it was surfed; the
 * decision taken with Miguel is that the session states that **here**, rather than hedging
 * every number. A hero that reads "22 (proposed?)" next to a tile that reads "3.4 km
 * (proposed?)" has turned honesty into noise and taught the reader to skip it.
 *
 * So: dismissible, shown once per browser, and the only place the caveat appears.
 */
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

const SEEN_KEY = "surf.method-banner.dismissed";

export function MethodBanner() {
  const t = useT();
  // Hidden until we know it has not been dismissed, so it cannot flash on a return visit.
  const [shown, setShown] = useState(false);

  useEffect(() => {
    try {
      setShown(window.localStorage.getItem(SEEN_KEY) !== "1");
    } catch {
      // Storage blocked: show it. Repeating the caveat is the safe failure here.
      setShown(true);
    }
  }, []);

  if (!shown) return null;

  const dismiss = () => {
    setShown(false);
    try {
      window.localStorage.setItem(SEEN_KEY, "1");
    } catch {
      // It will come back next visit. That is acceptable; silently dropping it is not.
    }
  };

  return (
    <aside className="method-banner">
      <span className="method-strip" aria-hidden="true" />
      <div>
        <p className="method-eyebrow">{t("method.eyebrow")}</p>
        <p className="method-body">{t("method.body")}</p>
      </div>
      <button type="button" className="button-primary" onClick={dismiss}>
        {t("method.dismiss")}
      </button>
    </aside>
  );
}
