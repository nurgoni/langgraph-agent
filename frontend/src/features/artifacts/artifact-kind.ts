/**
 * Jenis preview artifact dan format ukurannya (FR-50).
 */
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";

export type ArtifactKind = "image" | "csv" | "pdf" | "text" | "other";

const TEXT_MIME_TYPES = new Set(["application/json", "application/xml", "application/x-yaml"]);
const CSV_MIME_TYPES = new Set(["text/csv", "application/csv"]);
const BYTES_PER_KILOBYTE = 1024;
const SIZE_UNITS = ["B", "KB", "MB", "GB"] as const;

/** Cara menampilkan artifact di panel, dari tipe konten dan ekstensi nama file. */
export function artifactKind(artifact: Pick<ArtifactRef, "mime_type" | "name">): ArtifactKind {
  const mimeType = artifact.mime_type.toLowerCase();
  const name = artifact.name.toLowerCase();
  if (mimeType.startsWith("image/")) {
    return "image";
  }
  if (CSV_MIME_TYPES.has(mimeType) || name.endsWith(".csv")) {
    return "csv";
  }
  if (mimeType === "application/pdf") {
    return "pdf";
  }
  if (mimeType.startsWith("text/") || TEXT_MIME_TYPES.has(mimeType)) {
    return "text";
  }
  return "other";
}

/** Ukuran file yang mudah dibaca, misalnya `19.3 KB`. */
export function formatSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= BYTES_PER_KILOBYTE && unit < SIZE_UNITS.length - 1) {
    value /= BYTES_PER_KILOBYTE;
    unit += 1;
  }
  const rounded = unit === 0 ? String(value) : value.toFixed(1);
  return `${rounded} ${SIZE_UNITS[unit]}`;
}
