/**
 * Form project (FR-44): nama, deskripsi, agent dasar, model, instruksi, skill, dan batas token.
 * Memakai komponen form shadcn (react-hook-form + zod, keputusan user F34). Dipakai halaman
 * buat project dan edit project.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { useServiceInfo } from "@/api/service-info";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  type ProjectFormValues,
  projectFormSchema,
  SERVICE_DEFAULT_MODEL,
} from "@/features/projects/project-form";
import type { SkillSummary } from "@/features/projects/projects-service";
import { useSkills } from "@/features/projects/use-projects";

const INSTRUCTIONS_ROWS = 8;

export interface ProjectFormProps {
  initialValues: ProjectFormValues;
  /** Agent dasar tidak bisa diganti setelah project dibuat. */
  agentLocked: boolean;
  submitLabel: string;
  isSubmitting: boolean;
  /** Pesan error dari service, misalnya model atau skill yang tidak dikenal. */
  submitError: string | null;
  onSubmit: (values: ProjectFormValues) => void;
  onCancel: () => void;
}

export function ProjectForm(props: ProjectFormProps) {
  const { initialValues, agentLocked, submitLabel, isSubmitting, submitError } = props;
  const info = useServiceInfo();
  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: initialValues,
  });
  const submit = form.handleSubmit(props.onSubmit);
  const agents = info.data?.agents ?? [];
  const models = info.data?.models ?? [];

  return (
    <Form {...form}>
      <form onSubmit={(event) => void submit(event)} className="grid gap-6">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="baseAgentId"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Agent</FormLabel>
              <Select value={field.value} onValueChange={field.onChange} disabled={agentLocked}>
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {agents.map((agent) => (
                    <SelectItem key={agent.key} value={agent.key}>
                      {agent.key}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                {agentLocked
                  ? "The agent cannot be changed after the project is created."
                  : "The agent that runs every chat in this project."}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="model"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Model</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value={SERVICE_DEFAULT_MODEL}>Service default</SelectItem>
                  {models.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>Users can still pick another model in each chat.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="instructions"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Instructions</FormLabel>
              <FormControl>
                <Textarea rows={INSTRUCTIONS_ROWS} {...field} />
              </FormControl>
              <FormDescription>Added to the system prompt of every chat.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <SkillsField form={form} />
        <FormField
          control={form.control}
          name="maxTokens"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Answer token limit</FormLabel>
              <FormControl>
                <Input inputMode="numeric" placeholder="Service default" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {submitError !== null && (
          <p role="alert" className="text-sm text-destructive">
            {submitError}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={props.onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Form>
  );
}

interface SkillsFieldProps {
  form: ReturnType<typeof useForm<ProjectFormValues>>;
}

/** Checkbox per skill dari `GET /skills`, ditambah skill aktif yang tidak ada di katalog. */
function SkillsField({ form }: SkillsFieldProps) {
  const skills = useSkills();
  return (
    <FormField
      control={form.control}
      name="skillIds"
      render={({ field }) => (
        <FormItem>
          <FormLabel asChild>
            <legend>Skills</legend>
          </FormLabel>
          {skills.isError && (
            <p role="alert" className="text-sm text-destructive">
              {skills.error.message}
            </p>
          )}
          <fieldset className="grid gap-3" aria-label="Skills">
            {skillOptions(skills.data ?? [], field.value).map((skill) => (
              <label key={skill.id} className="flex items-start gap-3 text-sm">
                <Checkbox
                  aria-label={skill.name}
                  checked={field.value.includes(skill.id)}
                  onCheckedChange={(checked) =>
                    field.onChange(toggled(field.value, skill.id, checked === true))
                  }
                />
                <span className="grid gap-0.5">
                  <span className="font-medium">{skill.name}</span>
                  <span className="text-muted-foreground">{skill.description}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <FormDescription>The agent loads an active skill when a task needs it.</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

interface SkillOption {
  id: string;
  name: string;
  description: string;
}

/** Skill katalog, lalu skill aktif yang tidak (lagi) ada di katalog supaya bisa dilepas. */
function skillOptions(catalog: SkillSummary[], selected: string[]): SkillOption[] {
  const options: SkillOption[] = [...catalog];
  const known = new Set(catalog.map((skill) => skill.id));
  for (const skillId of selected) {
    if (!known.has(skillId)) {
      options.push({ id: skillId, name: skillId, description: "Not available in this service." });
    }
  }
  return options;
}

function toggled(selected: string[], skillId: string, checked: boolean): string[] {
  if (checked) {
    return selected.includes(skillId) ? selected : [...selected, skillId];
  }
  return selected.filter((id) => id !== skillId);
}
