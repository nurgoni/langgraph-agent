/**
 * Ringkasan project di layar chat kosong (FR-44): nama, aksi edit/hapus (bukan untuk built-in),
 * instruksi, skill aktif, dan daftar chat di project.
 */
import { useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ProjectBadge } from "@/features/projects/ProjectBadge";
import type { Project } from "@/features/projects/projects-service";
import { useDeleteProject } from "@/features/projects/use-projects";
import { ThreadActions } from "@/features/threads/ThreadActions";
import {
  chatPath,
  editProjectPath,
  PROJECTS_PATH,
  threadsQueryKey,
} from "@/features/threads/thread-paths";
import { useThreads } from "@/features/threads/use-threads";

export function ProjectOverview({ project }: { project: Project }) {
  return (
    <div className="grid gap-6 text-left">
      <header className="grid gap-1">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-2xl font-medium tracking-tight">{project.name}</h1>
          <ProjectBadge project={project} />
          {!project.read_only && <ProjectMenu project={project} />}
        </div>
        {project.description !== "" && (
          <p className="text-muted-foreground">{project.description}</p>
        )}
      </header>
      <ProjectDetails project={project} />
      <ProjectChats projectId={project.id} />
    </div>
  );
}

function ProjectDetails({ project }: { project: Project }) {
  return (
    <dl className="grid gap-3 text-sm">
      <div className="grid gap-1">
        <dt className="font-medium">Instructions</dt>
        <dd className="line-clamp-3 whitespace-pre-wrap text-muted-foreground">
          {project.instructions || "No instructions."}
        </dd>
      </div>
      <div className="grid gap-1">
        <dt className="font-medium">Skills</dt>
        <dd className="flex flex-wrap gap-1">
          {project.skill_ids.length === 0 && (
            <span className="text-muted-foreground">No skills.</span>
          )}
          {project.skill_ids.map((skillId) => (
            <Badge key={skillId} variant="outline">
              {skillId}
            </Badge>
          ))}
        </dd>
      </div>
    </dl>
  );
}

function ProjectChats({ projectId }: { projectId: string }) {
  const threads = useThreads(projectId);
  return (
    <section className="grid gap-2" aria-label="Chats in this project">
      <h2 className="text-sm font-medium">Chats</h2>
      {threads.isError && (
        <p role="alert" className="text-sm text-destructive">
          {threads.error.message}
        </p>
      )}
      {threads.isSuccess && threads.data.length === 0 && (
        <p className="text-sm text-muted-foreground">No chats yet. Send a message to start one.</p>
      )}
      {threads.isSuccess && threads.data.length > 0 && (
        <ul className="divide-y rounded-md border">
          {threads.data.map((thread) => (
            <li key={thread.thread_id} className="flex items-center gap-2 px-3 py-2">
              <Link
                to={chatPath(projectId, thread.thread_id)}
                className="min-w-0 flex-1 truncate text-sm hover:underline"
              >
                {thread.title}
              </Link>
              <ThreadActions
                thread={thread}
                projectId={projectId}
                trigger={
                  <Button variant="ghost" size="icon" aria-label={`Actions for ${thread.title}`}>
                    <MoreHorizontal />
                  </Button>
                }
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProjectMenu({ project }: { project: Project }) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Project actions">
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem asChild>
            <Link to={editProjectPath(project.id)}>
              <Pencil />
              Edit project
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => setConfirmingDelete(true)}>
            <Trash2 />
            Delete project
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {confirmingDelete && (
        <DeleteProjectDialog project={project} onClose={() => setConfirmingDelete(false)} />
      )}
    </>
  );
}

function DeleteProjectDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const remove = useDeleteProject();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = () =>
    remove.mutate(project.id, {
      onSuccess: () => {
        queryClient.removeQueries({ queryKey: threadsQueryKey(project.id) });
        void navigate(PROJECTS_PATH);
      },
    });
  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete project?</AlertDialogTitle>
          <AlertDialogDescription>
            &ldquo;{project.name}&rdquo; and all of its chats will be deleted permanently.
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
              confirm();
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
