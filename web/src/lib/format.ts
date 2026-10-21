/**
 * Numbers and dates, through `Intl`.
 *
 * Not a nicety. Portuguese writes a decimal comma and orders dates differently, so a
 * hand-rolled `toFixed(1)` produces a number that is wrong in the locale the design was
 * drawn for. Every figure on screen goes through here.
 */
import type { LocaleTag, Messages } from "./i18n/catalog";

export function decimal(locale: LocaleTag, value: number, digits = 1): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function integer(locale: LocaleTag, value: number): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
}

export function percent(locale: LocaleTag, fraction: number, digits = 0): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(fraction);
}

/** A session start, as a person would write it. */
export function dateTime(locale: LocaleTag, unixSeconds: number): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "long",
    timeStyle: "short",
  }).format(new Date(unixSeconds * 1000));
}

/** Whole minutes, for a duration. Surf sessions are an hour; seconds are noise here. */
export function minutes(locale: LocaleTag, seconds: number): string {
  return integer(locale, Math.round(seconds / 60));
}

/** m/s to km/h. The pipeline is SI; the design is drawn in km/h, and that is a display choice. */
const KMH_PER_MS = 3.6;

export function kmh(locale: LocaleTag, metresPerSecond: number, digits = 1): string {
  return decimal(locale, metresPerSecond * KMH_PER_MS, digits);
}

/**
 * A distance and the unit it should be read in, because 752 m and 0.8 km are the same
 * number said with different precision and the design says the shorter one.
 *
 * The unit comes back as a message key rather than a string: no component holds a literal,
 * and Portuguese and English happen to agree on "m" and "km" only until they do not.
 */
export function distance(
  locale: LocaleTag,
  metres: number,
): { value: string; unit: keyof Messages } {
  if (metres < 1000) return { value: integer(locale, metres), unit: "unit.metres" };
  return { value: decimal(locale, metres / 1000), unit: "unit.km" };
}
