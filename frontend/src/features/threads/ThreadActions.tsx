/**
 * Menu aksi satu thread (FR-44): rename lewat dialog form, dan hapus dengan konfirmasi. Dipakai
 * di Recents (sidebar) dan daftar chat halaman project.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Trash2 } from "lucide-react";
import { type ReactElement, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router";
import { z } from "zod";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { newChatPath } from "@/features/threads/thread-paths";
import type { ThreadSummary } from "@/features/threads/threads-service";
import { useDeleteThread, useRenameThread } from "@/features/threads/use-threads";

/** Batas judul thread di service (`ThreadRenameInput.title`). */
const THREAD_TITLE_MAX_LENGTH = 60;

const renameSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Enter a title.")
    .max(THREAD_TITLE_MAX_LENGTH, `Use at most ${THREAD_TITLE_MAX_LENGTH} characters.`),
});
type RenameValues = z.infer<typeof renameSchema>;

type OpenDialog = "rename" | "delete" | null;

export interface ThreadActionsProps {
  thread: ThreadSummary;
  /** Project thread, atau `null` untuk chat umum. */
  projectId: string | null;
  /** Tombol pembuka menu, dipasang lewat `asChild`. */
  trigger: ReactElement;
}

export function ThreadActions({ thread, projectId, trigger }: ThreadActionsProps) {
  const [openDialog, setOpenDialog] = useState<OpenDialog>(null);
  const close = () => setOpenDialog(null);
  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => setOpenDialog("rename")}>
            <Pencil />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => setOpenDialog("delete")}>
            <Trash2 />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {openDialog === "rename" && (
        <RenameThreadDialog thread={thread} projectId={projectId} onClose={close} />
      )}
      {openDialog === "delete" && (
        <DeleteThreadDialog thread={thread} projectId={projectId} onClose={close} />
      )}
    </>
  );
}

interface ThreadDialogProps {
  thread: ThreadSummary;
  projectId: string | null;
  onClose: () => void;
}

function RenameThreadDialog({ thread, projectId, onClose }: ThreadDialogProps) {
  const rename = useRenameThread(projectId);
  const form = useForm<RenameValues>({
    resolver: zodResolver(renameSchema),
    defaultValues: { title: thread.title },
  });
  const submit = form.handleSubmit(async ({ title }) => {
    try {
      await rename.mutateAsync({ threadId: thread.thread_id, title });
    } catch {
      // Pesan error tampil dari `rename.error`; dialog tetap terbuka supaya user bisa mengulang.
      return;
    }
    onClose();
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename chat</DialogTitle>
          <DialogDescription>Give this conversation a name you will recognize.</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={(event) => void submit(event)} className="grid gap-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title</FormLabel>
                  <FormControl>
                    <Input autoFocus {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {rename.isError && (
              <p role="alert" className="text-sm text-destructive">
                {rename.error.message}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={rename.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteThreadDialog({ thread, projectId, onClose }: ThreadDialogProps) {
  const remove = useDeleteThread(projectId);
  const { threadId: openThreadId } = useParams();
  const navigate = useNavigate();
  const confirm = async () => {
    try {
      await remove.mutateAsync(thread.thread_id);
    } catch {
      // Pesan error tampil dari `remove.error`; dialog tetap terbuka.
      return;
    }
    onClose();
    if (openThreadId === thread.thread_id) {
      void navigate(newChatPath(projectId));
    }
  };
  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete chat?</AlertDialogTitle>
          <AlertDialogDescription>
            &ldquo;{thread.title}&rdquo; and its messages will be deleted permanently.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {remove.isError && (
          <p role="alert" className="text-sm text-destructive">
            {remove.error.message}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={remove.isPending}
            onClick={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
