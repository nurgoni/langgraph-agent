/**
 * Unduh artifact dari object URL, karena link langsung ke `/api/artifacts/{id}` tidak membawa
 * token (token ada di header, bukan cookie).
 */
import { objectUrlFor } from "@/features/artifacts/use-artifact-content";

/** Simpan `blob` sebagai file bernama `name` lewat link unduh sementara. */
export function saveBlob(blob: Blob, name: string): void {
  const link = document.createElement("a");
  link.href = objectUrlFor(blob);
  link.download = name;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
}
