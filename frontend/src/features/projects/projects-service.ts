/**
 * Request project (FR-36, ADR 0004) dan katalog skill (FR-38) ke agent service.
 */
import type { ApiClient } from "@/api/client";
import type { components } from "@/api/schema";
import { requireData, requireOk } from "@/api/service-error";

export type Project = components["schemas"]["Project"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectUpdate = components["schemas"]["ProjectUpdate"];
export type SkillSummary = components["schemas"]["SkillSummary"];

const LIST_FAILED_MESSAGE = "Cannot load projects.";
const GET_FAILED_MESSAGE = "Cannot load this project.";
const SAVE_FAILED_MESSAGE = "Cannot save this project.";
const DELETE_FAILED_MESSAGE = "Cannot delete this project.";
const SKILLS_FAILED_MESSAGE = "Cannot load skills.";

/**
 * CRUD project dan daftar skill.
 *
 * Class karena semua method memakai dependency yang sama (`api`). Semua method melempar
 * `ServiceError` jika service menolak request (misalnya 404 atau 422) atau tidak terjangkau.
 */
export class ProjectsService {
  private readonly api: ApiClient;

  /** @param api Client bertipe ke agent service. */
  constructor(api: ApiClient) {
    this.api = api;
  }

  /** Project built-in lebih dulu, lalu milik user, terbaru diubah lebih dulu. */
  async list(): Promise<Project[]> {
    const list = await requireData(() => this.api.GET("/projects"), LIST_FAILED_MESSAGE);
    return list.projects;
  }

  async get(projectId: string): Promise<Project> {
    return requireData(
      () => this.api.GET("/projects/{project_id}", { params: { path: { project_id: projectId } } }),
      GET_FAILED_MESSAGE,
    );
  }

  async create(project: ProjectCreate): Promise<Project> {
    return requireData(() => this.api.POST("/projects", { body: project }), SAVE_FAILED_MESSAGE);
  }

  async update(projectId: string, changes: ProjectUpdate): Promise<Project> {
    return requireData(
      () =>
        this.api.PATCH("/projects/{project_id}", {
          params: { path: { project_id: projectId } },
          body: changes,
        }),
      SAVE_FAILED_MESSAGE,
    );
  }

  async remove(projectId: string): Promise<void> {
    await requireOk(
      () =>
        this.api.DELETE("/projects/{project_id}", { params: { path: { project_id: projectId } } }),
      DELETE_FAILED_MESSAGE,
    );
  }

  /** Skill yang bisa diaktifkan di project (`GET /skills`). */
  async listSkills(): Promise<SkillSummary[]> {
    const list = await requireData(() => this.api.GET("/skills"), SKILLS_FAILED_MESSAGE);
    return list.skills;
  }
}
