"use client";

import { useEffect, type RefObject } from "react";

/**
 * After a failed submit, moves focus to the first field the API complained about
 * (`aria-invalid`), or to the error alert when the failure is not about a field,
 * so keyboard and screen-reader users land on what needs attention.
 */
export function useFocusOnError(error: unknown, container: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (error === null) return;
    container.current
      ?.querySelector<HTMLElement>('[aria-invalid="true"], [role="alert"]')
      ?.focus();
  }, [error, container]);
}
