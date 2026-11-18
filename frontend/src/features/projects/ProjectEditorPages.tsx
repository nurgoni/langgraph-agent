/**
 * Halaman `/projects/new` dan `/projects/:projectId/edit` (FR-44). Project built-in read-only,
 * jadi halaman edit-nya hanya menampilkan pemberitahuan.
 */
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router";

import { useServiceInfo } from "@/api/service-info";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  newProjectValues,
  projectValues,
  toProjectCreate,
  toProjectUpdate,
} from "@/features/projects/project-form";
import { ProjectForm } from "@/features/projects/ProjectForm";
import { useCreateProject, useProject, useUpdateProject } from "@/features/projects/use-projects";
import { PROJECTS_PATH, projectPath } from "@/features/threads/thread-paths";

const READ_ONLY_MESSAGE = "Built-in projects are read-only.";

export function NewProjectPage() {
  const navigate = useNavigate();
  const info = useServiceInfo();
  const create = useCreateProject();
  return (
    <EditorLayout title="New project">
      {info.isPending && <Skeleton className="h-64 w-full" />}
      {info.isError && <ErrorAlert message={info.error.message} />}
      {info.isSuccess && (
        <ProjectForm
          initialValues={newProjectValues(info.data.default_agent)}
          agentLocked={false}
          submitLabel="Create project"
          isSubmitting={create.isPending}
          submitError={create.error?.message ?? null}
          onSubmit={(values) =>
            create.mutate(toProjectCreate(values), {
              onSuccess: (project) => void navigate(projectPath(project.id)),
            })
          }
          onCancel={() => void navigate(PROJECTS_PATH)}
        />
      )}
    </EditorLayout>
  );
}

export function EditProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const update = useUpdateProject(projectId);
  const backToProject = () => void navigate(projectPath(projectId));
  return (
    <EditorLayout title="Edit project">
      {project.isPending && <Skeleton className="h-64 w-full" />}
      {project.isError && <ErrorAlert message={project.error.message} />}
      {project.isSuccess && project.data.read_only && <ErrorAlert message={READ_ONLY_MESSAGE} />}
      {project.isSuccess && !project.data.read_only && (
        <ProjectForm
          initialValues={projectValues(project.data)}
          agentLocked
          submitLabel="Save changes"
          isSubmitting={update.isPending}
          submitError={update.error?.message ?? null}
          onSubmit={(values) => update.mutate(toProjectUpdate(values), { onSuccess: backToProject })}
          onCancel={backToProject}
        />
      )}
    </EditorLayout>
  );
}

function EditorLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="overflow-y-auto">
      <div className="mx-auto grid w-full max-w-2xl gap-6 p-6">
        <h1 className="text-2xl font-medium tracking-tight">{title}</h1>
        {children}
      </div>
    </div>
  );
}

function ErrorAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTitle>{message}</AlertTitle>
    </Alert>
  );
}
