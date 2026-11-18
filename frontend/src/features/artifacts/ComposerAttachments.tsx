/**
 * Lampiran di composer (FR-50): tombol pilih file dan chip per file dengan status upload. Disusun
 * dari primitive assistant-ui dan komponen shadcn, tanpa template registry `attachment` yang
 * butuh dependency tambahan (keputusan F38).
 */
import { AttachmentPrimitive, ComposerPrimitive, useAuiState } from "@assistant-ui/react";
import { AlertCircle, Loader2, Paperclip, X } from "lucide-react";

import { TooltipIconButton } from "@/components/assistant-ui/elements/tooltip-icon-button";
import { Button } from "@/components/ui/button";

export function ComposerAddAttachment() {
  return (
    <ComposerPrimitive.AddAttachment asChild>
      <TooltipIconButton
        tooltip="Attach files"
        side="bottom"
        variant="ghost"
        size="icon"
        className="size-7 rounded-full"
        aria-label="Attach files"
      >
        <Paperclip className="size-4" />
      </TooltipIconButton>
    </ComposerPrimitive.AddAttachment>
  );
}

export function ComposerAttachments() {
  return (
    <div className="flex w-full flex-wrap gap-2 empty:hidden" aria-label="Attachments">
      <ComposerPrimitive.Attachments>{() => <AttachmentChip />}</ComposerPrimitive.Attachments>
    </div>
  );
}

function AttachmentChip() {
  const name = useAuiState((s) => s.attachment.name);
  const status = useAuiState((s) => s.attachment.status);
  const uploading = status.type === "running";
  const error = status.type === "incomplete" ? (status.message ?? "Upload failed") : null;
  return (
    <AttachmentPrimitive.Root
      className="bg-muted flex max-w-60 items-center gap-1.5 rounded-md border py-1 ps-2 pe-1 text-sm"
      aria-label={`${name}${uploading ? ", uploading" : ""}${error === null ? "" : ", upload failed"}`}
    >
      {uploading && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
      {error !== null && <AlertCircle className="text-destructive size-3.5" aria-hidden="true" />}
      <span className="truncate">{name}</span>
      {error !== null && (
        <span role="alert" className="text-destructive truncate text-xs">
          {error}
        </span>
      )}
      <AttachmentPrimitive.Remove asChild>
        <Button variant="ghost" size="icon" className="size-5" aria-label={`Remove ${name}`}>
          <X className="size-3" />
        </Button>
      </AttachmentPrimitive.Remove>
    </AttachmentPrimitive.Root>
  );
}
