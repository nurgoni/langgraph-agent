/**
 * Gambar di markdown jawaban asisten (keputusan user F38). Model kadang menulis
 * `![chart](chart.png)` dengan path workspace yang tidak bisa dimuat browser. Jika nama filenya
 * cocok dengan artifact gambar yang dibagikan di jawaban yang sama, gambar ditampilkan dari
 * artifact itu (fetch bertoken). Path relatif lain tidak dimuat; URL absolut tetap seperti biasa.
 */
import { useAuiState } from "@assistant-ui/react";
import type { ComponentProps } from "react";

import { artifactKind } from "@/features/artifacts/artifact-kind";
import { useArtifactPanel } from "@/features/artifacts/artifact-panel-context";
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";
import { artifactsFromParts } from "@/features/artifacts/message-artifacts";
import { useArtifactContent } from "@/features/artifacts/use-artifact-content";

const ABSOLUTE_URL = /^(https?:|data:|blob:)/i;

export function ArtifactMarkdownImage({ src, alt }: ComponentProps<"img">) {
  const content = useAuiState((s) => s.message.content);
  if (typeof src !== "string" || src === "") {
    return null;
  }
  if (ABSOLUTE_URL.test(src)) {
    return <img src={src} alt={alt ?? ""} className="max-w-full rounded-md" />;
  }
  const match = matchingImage(src, artifactsFromParts(content));
  if (match === undefined) {
    return <span className="text-muted-foreground italic">[{alt || src}]</span>;
  }
  return <ArtifactInlineImage artifact={match} alt={alt ?? match.name} />;
}

function ArtifactInlineImage({ artifact, alt }: { artifact: ArtifactRef; alt: string }) {
  const content = useArtifactContent(artifact);
  const panel = useArtifactPanel();
  if (!content.isSuccess) {
    return <span className="text-muted-foreground italic">[{alt}]</span>;
  }
  return (
    <button type="button" className="my-2 block cursor-zoom-in" onClick={() => panel.open(artifact)}>
      <img src={content.data.url} alt={alt} className="max-h-96 max-w-full rounded-md border" />
    </button>
  );
}

/** Artifact gambar yang namanya sama dengan nama file di `src` (tanpa folder). */
function matchingImage(src: string, artifacts: readonly ArtifactRef[]): ArtifactRef | undefined {
  const fileName = decodeURIComponent(src.split(/[?#]/)[0] ?? "")
    .split("/")
    .pop();
  return artifacts.find(
    (artifact) => artifact.name === fileName && artifactKind(artifact) === "image",
  );
}
