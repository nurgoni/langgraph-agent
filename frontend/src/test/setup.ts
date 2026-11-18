// Matcher DOM (`toBeInTheDocument`) untuk Vitest, dan pembersihan DOM setelah setiap test.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom tidak punya matchMedia, padahal sidebar shadcn (`useIsMobile`) memakainya.
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}

// jsdom tidak punya ResizeObserver dan scroll, padahal viewport assistant-ui memakainya (F33).
if (typeof window.ResizeObserver !== "function") {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
for (const method of ["scrollTo", "scrollIntoView"]) {
  if (!Object.hasOwn(Element.prototype, method)) {
    Object.defineProperty(Element.prototype, method, { value: () => undefined, writable: true });
  }
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});
