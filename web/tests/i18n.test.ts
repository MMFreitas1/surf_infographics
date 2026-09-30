import { describe, expect, it } from "vitest";
import { decimal, integer, minutes, percent } from "@/lib/format";
import { matchLocale } from "@/lib/i18n";
import { DEFAULT_LOCALE, LOCALES, type Messages } from "@/lib/i18n/catalog";
import { en } from "@/lib/i18n/en";
import { ptPT } from "@/lib/i18n/pt-PT";

/**
 * The decision this file defends: the UI follows the system locale and no component holds a
 * string literal (PLAN.md, 2026-09-15). `tsc` already fails a catalogue missing a key,
 * because `Messages` is closed — these cover what the type cannot.
 */
describe("message catalogues", () => {
  it("cover exactly the same keys", () => {
    expect(Object.keys(ptPT).sort()).toEqual(Object.keys(en).sort());
  });

  it("leave no message empty in any locale", () => {
    for (const catalogue of [ptPT, en]) {
      for (const [key, value] of Object.entries(catalogue)) {
        expect(value.length, `${key} is empty`).toBeGreaterThan(0);
      }
    }
  });

  it("keep every placeholder a translation could silently drop", () => {
    const placeholders = (s: string) => (s.match(/\{(\w+)\}/g) ?? []).sort();
    for (const key of Object.keys(en) as (keyof Messages)[]) {
      expect(placeholders(ptPT[key]), `${key} placeholders differ`).toEqual(placeholders(en[key]));
    }
  });

  it("says nothing about validated accuracy outside the method banner", () => {
    // ADR-0013's bargain: the caveat is stated once per session, in the banner, so the
    // screen is honest without being a wall of hedging. If the word starts appearing on
    // individual figures, that decision has quietly been reversed.
    for (const catalogue of [ptPT, en]) {
      for (const [key, value] of Object.entries(catalogue)) {
        // `hero.ofProposals` is exempt and the distinction matters: "of 22 proposals"
        // names what L3 produced, which is the transparency the hero is supposed to
        // carry. What ADR-0013 rations is hedging *the count itself*.
        if (key.startsWith("method.")) continue;
        if (key === "hero.proposed" || key === "hero.ofProposals") continue;
        expect(value.toLowerCase(), `${key} hedges outside the banner`).not.toMatch(
          /proposta|proposed|validad|validated/,
        );
      }
    }
  });

  it("does not claim a model decided any number", () => {
    // ADR-0016 and ADR-0017: the cleaner, the audit and the wave count are deterministic.
    // The design's own banner said an LLM cleans and normalises the data; it does not.
    for (const catalogue of [ptPT, en]) {
      expect(catalogue["method.body"].toLowerCase()).toMatch(
        /determinístic|determinist|nenhum modelo|no model/,
      );
    }
  });
});

describe("locale resolution", () => {
  it("matches an exact tag", () => {
    expect(matchLocale("pt-PT")).toBe("pt-PT");
    expect(matchLocale("en")).toBe("en");
  });

  it("matches on language when the region differs", () => {
    // A rough match in the right language beats an exact match in the wrong one.
    expect(matchLocale("pt-BR")).toBe("pt-PT");
    expect(matchLocale("en-GB")).toBe("en");
  });

  it("is case-insensitive, because browsers are not consistent", () => {
    expect(matchLocale("PT-pt")).toBe("pt-PT");
  });

  it("returns null for a language with no catalogue, rather than guessing", () => {
    expect(matchLocale("ja")).toBeNull();
    expect(matchLocale(undefined)).toBeNull();
    expect(matchLocale("")).toBeNull();
  });

  it("ships a catalogue for every locale it claims to support", () => {
    for (const tag of LOCALES) expect(matchLocale(tag)).toBe(tag);
    expect(LOCALES).toContain(DEFAULT_LOCALE);
  });
});

describe("Intl formatting", () => {
  it("writes a decimal comma in Portuguese and a point in English", () => {
    // Not a nicety: toFixed(1) produces a number that is wrong in the locale the design
    // was drawn for.
    expect(decimal("pt-PT", 3.4)).toBe("3,4");
    expect(decimal("en", 3.4)).toBe("3.4");
  });

  it("rounds an integer without inventing precision", () => {
    expect(integer("en", 11.6)).toBe("12");
    expect(integer("pt-PT", 11.6)).toBe("12");
  });

  it("groups thousands the way each locale actually does", () => {
    // pt-PT sets minimumGroupingDigits to 2, so a four-digit number is *not* grouped --
    // a session's 3790 samples stay "3790" there and become "3,790" in English. Asserted
    // because it looks like a bug the first time you see it next to the English build.
    expect(integer("pt-PT", 3790)).toBe("3790");
    expect(integer("en", 3790)).toBe("3,790");
    expect(integer("pt-PT", 37900)).toBe("37 900".replace(" ", "\u00a0"));
  });

  it("formats coverage as a percentage", () => {
    expect(percent("en", 0.4813)).toBe("48%");
    expect(percent("en", 0.4813, 1)).toBe("48.1%");
  });

  it("reports a duration in whole minutes", () => {
    expect(minutes("en", 3300)).toBe("55");
  });
});
