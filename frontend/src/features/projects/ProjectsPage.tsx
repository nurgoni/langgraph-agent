/**
 * Halaman `/projects` (FR-44): project built-in dan milik user, dengan tombol buat project.
 */
import { Plus } from "lucide-react";
import { Link } from "react-router";

import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectBadge } from "@/features/projects/ProjectBadge";
import { useProjects } from "@/features/projects/use-projects";
import { NEW_PROJECT_PATH, projectPath } from "@/features/threads/thread-paths";

export function ProjectsPage() {
  const projects = useProjects();
  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-medium tracking-tight">Projects</h1>
        <Button asChild>
          <Link to={NEW_PROJECT_PATH}>
            <Plus />
            New project
          </Link>
        </Button>
      </div>
      {projects.isPending && <Skeleton className="h-24 w-full" />}
      {projects.isError && (
        <Alert variant="destructive">
          <AlertTitle>{projects.error.message}</AlertTitle>
        </Alert>
      )}
      {projects.isSuccess && (
        <ul className="grid gap-3 sm:grid-cols-2" aria-label="Projects">
          {projects.data.map((project) => (
            <li key={project.id}>
              <Link to={projectPath(project.id)} className="block h-full">
                <Card className="h-full transition-colors hover:bg-accent">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between gap-2">
                      <span className="truncate">{project.name}</span>
                      <ProjectBadge project={project} />
                    </CardTitle>
                    <CardDescription className="line-clamp-2">
                      {project.description || "No description."}
                    </CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
