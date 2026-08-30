"use client";

import { useEffect } from "react";
import { reportError } from "@/lib/report-error";

/**
 * Mounted once in the root layout. Forwards uncaught errors and unhandled promise
 * rejections to the API's diagnostics buffer. Renders nothing.
 */
export function ErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      void reportError({
        message: event.message,
        kind: event.error?.name ?? "Error",
        stack: event.error?.stack ?? "",
        context: { source: event.filename, line: event.lineno, column: event.colno },
      });
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason as { message?: string; name?: string; stack?: string };
      void reportError({
        message: reason?.message ?? String(event.reason),
        kind: reason?.name ?? "UnhandledRejection",
        stack: reason?.stack ?? "",
        context: { source: "unhandledrejection" },
      });
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
