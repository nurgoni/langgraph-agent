/**
 * Hook TanStack Query untuk project dan skill.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/auth/auth-context";
import {
  type Project,
  type ProjectCreate,
  ProjectsService,
  type ProjectUpdate,
} from "@/features/projects/projects-service";

export const PROJECTS_QUERY_KEY = ["projects"] as const;
const SKILLS_QUERY_KEY = ["skills"] as const;

function useProjectsService(): ProjectsService {
  const { api } = useAuth();
  return new ProjectsService(api);
}

export function useProjects() {
  const service = useProjectsService();
  return useQuery({ queryKey: PROJECTS_QUERY_KEY, queryFn: () => service.list() });
}

export function useProject(projectId: string) {
  const service = useProjectsService();
  return useQuery({
    queryKey: [...PROJECTS_QUERY_KEY, projectId],
    queryFn: () => service.get(projectId),
  });
}

/** Katalog skill jarang berubah (dimuat saat startup service), jadi di-cache selama sesi. */
export function useSkills() {
  const service = useProjectsService();
  return useQuery({
    queryKey: SKILLS_QUERY_KEY,
    queryFn: () => service.listSkills(),
    staleTime: Infinity,
  });
}

export function useCreateProject() {
  const service = useProjectsService();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (project: ProjectCreate) => service.create(project),
    onSuccess: (project) => storeProject(queryClient, project),
  });
}

export function useUpdateProject(projectId: string) {
  const service = useProjectsService();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: ProjectUpdate) => service.update(projectId, changes),
    onSuccess: (project) => storeProject(queryClient, project),
  });
}

export function useDeleteProject() {
  const service = useProjectsService();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => service.remove(projectId),
    onSuccess: async (_, projectId) => {
      queryClient.removeQueries({ queryKey: [...PROJECTS_QUERY_KEY, projectId] });
      await queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY, exact: true });
    },
  });
}

/** Simpan project hasil mutation ke cache detail, lalu muat ulang daftar project. */
async function storeProject(
  queryClient: ReturnType<typeof useQueryClient>,
  project: Project,
): Promise<void> {
  queryClient.setQueryData([...PROJECTS_QUERY_KEY, project.id], project);
  await queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY, exact: true });
}
