/**
 * Isi panel preview (FR-50): gambar, tabel CSV (papaparse, keputusan user F38), PDF lewat viewer
 * bawaan browser, teks, atau pemberitahuan untuk jenis lain. Semua dibaca dari object URL hasil
 * fetch bertoken, jadi header `Content-Disposition: attachment` service tidak menghalangi preview.
 */
import Papa from "papaparse";

import { Alert, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { artifactKind } from "@/features/artifacts/artifact-kind";
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";
import { useArtifactContent } from "@/features/artifacts/use-artifact-content";

const CSV_PREVIEW_ROWS = 200;
const TEXT_PREVIEW_CHARS = 100_000;

export function ArtifactPreview({ artifact }: { artifact: ArtifactRef }) {
  const content = useArtifactContent(artifact);
  if (content.isPending) {
    return <Skeleton className="h-64 w-full" aria-label="Loading preview" />;
  }
  if (content.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{content.error.message}</AlertTitle>
      </Alert>
    );
  }
  const { url, text } = content.data;
  switch (artifactKind(artifact)) {
    case "image":
      return (
        <img src={url} alt={artifact.name} className="mx-auto max-h-full max-w-full object-contain" />
      );
    case "pdf":
      return <iframe src={url} title={artifact.name} className="h-full min-h-[70vh] w-full rounded-md border" />;
    case "csv":
      return <CsvTable text={text ?? ""} />;
    case "text":
      return (
        <pre className="bg-muted overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap">
          {(text ?? "").slice(0, TEXT_PREVIEW_CHARS)}
        </pre>
      );
    default:
      return <p className="text-muted-foreground text-sm">No preview for this file type. Download it to open it.</p>;
  }
}

function CsvTable({ text }: { text: string }) {
  const parsed = Papa.parse<string[]>(text, { skipEmptyLines: true });
  const [header = [], ...rows] = parsed.data;
  const shown = rows.slice(0, CSV_PREVIEW_ROWS);
  return (
    <Table aria-label="CSV preview">
      {rows.length > shown.length && (
        <TableCaption>
          Showing the first {shown.length} of {rows.length} rows.
        </TableCaption>
      )}
      <TableHeader>
        <TableRow>
          {header.map((cell, column) => (
            <TableHead key={column}>{cell}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {shown.map((row, index) => (
          <TableRow key={index}>
            {row.map((cell, column) => (
              <TableCell key={column}>{cell}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
