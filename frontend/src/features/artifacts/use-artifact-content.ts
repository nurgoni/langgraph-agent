/**
 * Isi artifact untuk preview: `Blob` dari `GET /artifacts/{id}` (dengan token), object URL-nya,
 * dan teks untuk CSV atau file teks. Di-cache TanStack Query, karena isi artifact tidak berubah.
 */
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/auth/auth-context";
import { artifactKind } from "@/features/artifacts/artifact-kind";
import { type ArtifactRef, ArtifactsService } from "@/features/artifacts/artifacts-service";

export interface ArtifactContent {
  blob: Blob;
  /** Object URL untuk `<img>`, `<iframe>`, dan link unduh. */
  url: string;
  /** Isi teks untuk CSV dan file teks, atau `null` untuk jenis lain. */
  text: string | null;
}

// Satu object URL per blob, dipakai ulang selama blob ada di cache query. URL tidak dicabut:
// StrictMode menjalankan cleanup effect dua kali, dan jumlah artifact per sesi kecil.
const objectUrls = new WeakMap<Blob, string>();

export function objectUrlFor(blob: Blob): string {
  let url = objectUrls.get(blob);
  if (url === undefined) {
    url = URL.createObjectURL(blob);
    objectUrls.set(blob, url);
  }
  return url;
}

export function useArtifactContent(artifact: ArtifactRef) {
  const { api } = useAuth();
  return useQuery({
    queryKey: ["artifact-content", artifact.id],
    queryFn: async (): Promise<ArtifactContent> => {
      const blob = await new ArtifactsService(api).download(artifact.id);
      const kind = artifactKind(artifact);
      const text = kind === "csv" || kind === "text" ? await blob.text() : null;
      return { blob, url: objectUrlFor(blob), text };
    },
    staleTime: Infinity,
  });
}
