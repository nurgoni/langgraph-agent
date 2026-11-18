import { describe, expect, it } from "vitest";

import {
  MAX_PROJECT_SKILLS,
  newProjectValues,
  PROJECT_NAME_MAX_LENGTH,
  projectFormSchema,
  projectValues,
  SERVICE_DEFAULT_MODEL,
  toProjectCreate,
  toProjectUpdate,
} from "@/features/projects/project-form";
import { BUILTIN_PROJECT } from "@/test/fake-service";

function errorsFor(values: Partial<ReturnType<typeof newProjectValues>>): string[] {
  const result = projectFormSchema.safeParse({ ...newProjectValues("chatbot"), ...values });
  return result.success ? [] : result.error.issues.map((issue) => issue.path.join("."));
}

describe("projectFormSchema", () => {
  it("accepts a minimal project and trims the name", () => {
    const parsed = projectFormSchema.parse({ ...newProjectValues("chatbot"), name: "  Notes  " });

    expect(parsed.name).toBe("Notes");
  });

  it("rejects values outside the service limits", () => {
    expect(errorsFor({ name: " " })).toEqual(["name"]);
    expect(errorsFor({ name: "x".repeat(PROJECT_NAME_MAX_LENGTH + 1) })).toEqual(["name"]);
    expect(errorsFor({ name: "ok", skillIds: Array(MAX_PROJECT_SKILLS + 1).fill("builtin/a") })).toEqual(
      ["skillIds"],
    );
    expect(errorsFor({ name: "ok", maxTokens: "0" })).toEqual(["maxTokens"]);
    expect(errorsFor({ name: "ok", maxTokens: "1.5" })).toEqual(["maxTokens"]);
  });
});

describe("project payloads", () => {
  it("maps the service default model and empty token limit to null", () => {
    const values = { ...newProjectValues("chatbot"), name: "Notes", skillIds: ["builtin/a"] };

    expect(toProjectCreate(values)).toEqual({
      name: "Notes",
      description: "",
      base_agent_id: "chatbot",
      model: null,
      instructions: "",
      skill_ids: ["builtin/a"],
      settings: { max_tokens: null },
    });
  });

  it("round-trips an existing project without sending the base agent", () => {
    const project = { ...BUILTIN_PROJECT, model: "fake", settings: { max_tokens: 600 } };
    const values = projectValues(project);

    expect(values.model).toBe("fake");
    expect(values.maxTokens).toBe("600");
    expect(projectValues(BUILTIN_PROJECT).model).toBe(SERVICE_DEFAULT_MODEL);
    expect(toProjectUpdate(values)).toEqual({
      name: project.name,
      description: project.description,
      model: "fake",
      instructions: project.instructions,
      skill_ids: project.skill_ids,
      settings: { max_tokens: 600 },
    });
  });
});
