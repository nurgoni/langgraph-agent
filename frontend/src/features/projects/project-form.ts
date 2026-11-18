/**
 * Schema form project (zod) dan konversinya ke body API. Batas mengikuti `schema/projects.py`
 * di service, supaya kesalahan tampil di field sebelum request dikirim.
 *
 * Contoh: `toProjectCreate(newProjectValues("chatbot"))` menghasilkan body `POST /projects`.
 */
import { z } from "zod";

import type { Project, ProjectCreate, ProjectUpdate } from "@/features/projects/projects-service";

export const PROJECT_NAME_MAX_LENGTH = 80;
export const PROJECT_DESCRIPTION_MAX_LENGTH = 500;
export const PROJECT_INSTRUCTIONS_MAX_LENGTH = 8000;
export const MAX_PROJECT_SKILLS = 20;
/** Nilai `model` di form untuk "pakai default service" (Radix Select menolak nilai kosong). */
export const SERVICE_DEFAULT_MODEL = "__service_default__";
const WHOLE_NUMBER = /^\d*$/;

export const projectFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a name.")
    .max(PROJECT_NAME_MAX_LENGTH, `Use at most ${PROJECT_NAME_MAX_LENGTH} characters.`),
  description: z
    .string()
    .max(PROJECT_DESCRIPTION_MAX_LENGTH, `Use at most ${PROJECT_DESCRIPTION_MAX_LENGTH} characters.`),
  baseAgentId: z.string().min(1, "Choose an agent."),
  model: z.string(),
  instructions: z
    .string()
    .max(
      PROJECT_INSTRUCTIONS_MAX_LENGTH,
      `Use at most ${PROJECT_INSTRUCTIONS_MAX_LENGTH} characters.`,
    ),
  skillIds: z
    .array(z.string())
    .max(MAX_PROJECT_SKILLS, `Choose at most ${MAX_PROJECT_SKILLS} skills.`),
  maxTokens: z
    .string()
    .trim()
    .regex(WHOLE_NUMBER, "Enter a whole number.")
    .refine((value) => value === "" || Number(value) >= 1, "Use at least 1."),
});

export type ProjectFormValues = z.infer<typeof projectFormSchema>;

/** Nilai awal form project baru. */
export function newProjectValues(defaultAgentId: string): ProjectFormValues {
  return {
    name: "",
    description: "",
    baseAgentId: defaultAgentId,
    model: SERVICE_DEFAULT_MODEL,
    instructions: "",
    skillIds: [],
    maxTokens: "",
  };
}

/** Nilai form untuk mengedit project yang ada. */
export function projectValues(project: Project): ProjectFormValues {
  const maxTokens = project.settings.max_tokens;
  return {
    name: project.name,
    description: project.description,
    baseAgentId: project.base_agent_id,
    model: project.model ?? SERVICE_DEFAULT_MODEL,
    instructions: project.instructions,
    skillIds: [...project.skill_ids],
    maxTokens: maxTokens === null || maxTokens === undefined ? "" : String(maxTokens),
  };
}

/** Body `POST /projects` dari nilai form yang sudah divalidasi. */
export function toProjectCreate(values: ProjectFormValues): ProjectCreate {
  return { ...editableFields(values), base_agent_id: values.baseAgentId };
}

/**
 * Body `PATCH /projects/{id}`: semua field yang bisa diubah dikirim. `base_agent_id` tidak
 * termasuk karena tidak bisa diubah setelah project dibuat.
 */
export function toProjectUpdate(values: ProjectFormValues): ProjectUpdate {
  return editableFields(values);
}

function editableFields(values: ProjectFormValues): Omit<ProjectCreate, "base_agent_id"> {
  return {
    name: values.name,
    description: values.description,
    model: values.model === SERVICE_DEFAULT_MODEL ? null : values.model,
    instructions: values.instructions,
    skill_ids: values.skillIds,
    settings: { max_tokens: values.maxTokens === "" ? null : Number(values.maxTokens) },
  };
}
