/**
 * Numbers and dates, through `Intl`.
 *
 * Not a nicety. Portuguese writes a decimal comma and orders dates differently, so a
 * hand-rolled `toFixed(1)` produces a number that is wrong in the locale the design was
 * drawn for. Every figure on screen goes through here.
 */
import type { LocaleTag } from "./i18n/catalog";

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
