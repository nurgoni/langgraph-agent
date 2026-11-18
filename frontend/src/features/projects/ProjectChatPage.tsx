/**
 * Halaman project (FR-44): `/projects/:projectId` menampilkan ringkasan project, daftar chat, dan
 * composer untuk chat baru di project itu (keputusan user F34). `/projects/:projectId/chat/:id`
 * membuka ulang chat project.
 */
import { Link, useParams } from "react-router";

import { HTTP_NOT_FOUND, ServiceError } from "@/api/service-error";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ChatPage } from "@/features/chat/ChatPage";
import { ProjectOverview } from "@/features/projects/ProjectOverview";
import { useProject } from "@/features/projects/use-projects";
import { projectPath } from "@/features/threads/thread-paths";

const PROJECT_NOT_FOUND_MESSAGE = "This project was not found.";

export function ProjectChatPage() {
  const { projectId = "", threadId } = useParams();
  const project = useProject(projectId);

  if (project.isPending) {
    return <Skeleton className="m-6 h-64" />;
  }
  if (project.isError) {
    const notFound =
      project.error instanceof ServiceError && project.error.status === HTTP_NOT_FOUND;
    return (
      <div className="mx-auto w-full max-w-xl p-6">
        <Alert variant="destructive">
          <AlertTitle>{notFound ? PROJECT_NOT_FOUND_MESSAGE : project.error.message}</AlertTitle>
        </Alert>
      </div>
    );
  }
  // `key` per project: pindah project membuat controller chat baru dengan route project itu.
  return (
    <>
      {threadId !== undefined && (
        <nav aria-label="Breadcrumb" className="border-b px-4 py-2 text-sm">
          <Link to={projectPath(projectId)} className="text-muted-foreground hover:underline">
            {project.data.name}
          </Link>
        </nav>
      )}
      <ChatPage
        key={projectId}
        projectId={projectId}
        defaultModel={project.data.model}
        welcome={<ProjectOverview project={project.data} />}
      />
    </>
  );
}
