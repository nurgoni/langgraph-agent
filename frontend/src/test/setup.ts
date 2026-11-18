// Matcher DOM (`toBeInTheDocument`) untuk Vitest, dan pembersihan DOM setelah setiap test.
import "@testing-library/jest-dom/vitest";

import { File as NodeFile } from "node:buffer";

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

// Vitest mengubah setiap Blob jsdom di dalam FormData menjadi Blob Node tanpa nama file, sehingga
// upload artifact sampai ke service palsu sebagai "blob". File dan FormData memakai implementasi
// Node (sama dengan `Request`), jadi nama file utuh; Blob tetap milik jsdom (F38). Browser asli
// tidak terdampak.
const nodeFormData = (await new Response(new URLSearchParams("probe=1")).formData()).constructor;
Object.assign(globalThis, { File: NodeFile, FormData: nodeFormData });

// jsdom tidak punya object URL, padahal preview artifact memakainya (F38).
if (typeof URL.createObjectURL !== "function") {
  let nextUrl = 0;
  URL.createObjectURL = () => `blob:test/${(nextUrl += 1)}`;
  URL.revokeObjectURL = () => undefined;
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});
