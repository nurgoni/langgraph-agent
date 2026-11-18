/**
 * Penanda project built-in yang read-only (FR-36): dibagikan ke semua user dan tidak bisa diubah.
 */
import { Badge } from "@/components/ui/badge";
import type { Project } from "@/features/projects/projects-service";

const READ_ONLY_LABEL = "Built-in";

export function ProjectBadge({ project }: { project: Project }) {
  if (!project.read_only) {
    return null;
  }
  return (
    <Badge variant="secondary" title="Shared with every user. Read-only.">
      {READ_ONLY_LABEL}
    </Badge>
  );
}
