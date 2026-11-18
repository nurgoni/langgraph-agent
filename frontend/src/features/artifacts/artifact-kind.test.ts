import { describe, expect, it } from "vitest";

import { artifactKind, formatSize } from "@/features/artifacts/artifact-kind";

describe("artifactKind", () => {
  it.each([
    ["chart.png", "image/png", "image"],
    ["sales.csv", "text/csv", "csv"],
    ["export.csv", "application/octet-stream", "csv"],
    ["report.pdf", "application/pdf", "pdf"],
    ["notes.md", "text/markdown", "text"],
    ["data.json", "application/json", "text"],
    ["archive.zip", "application/zip", "other"],
  ])("%s (%s) is previewed as %s", (name, mimeType, kind) => {
    expect(artifactKind({ name, mime_type: mimeType })).toBe(kind);
  });
});

describe("formatSize", () => {
  it.each([
    [512, "512 B"],
    [19_341, "18.9 KB"],
    [26_214_400, "25.0 MB"],
  ])("%d bytes is %s", (bytes, text) => {
    expect(formatSize(bytes)).toBe(text);
  });
});
