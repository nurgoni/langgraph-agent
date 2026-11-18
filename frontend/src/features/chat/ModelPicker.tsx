/**
 * Pemilih model di composer (keputusan user F33: model saja, agent selalu `default_agent`).
 * Daftar model dan default dibaca dari `GET /info`.
 */
import { useQuery } from "@tanstack/react-query";

import { errorDetail } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const INFO_QUERY_KEY = ["info"] as const;

export interface ModelPickerProps {
  /** Model pilihan user, atau `null` untuk default service. */
  value: string | null;
  onChange: (model: string) => void;
}

export function ModelPicker({ value, onChange }: ModelPickerProps) {
  const { api } = useAuth();
  const info = useQuery({
    queryKey: INFO_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/info");
      if (data === undefined) {
        throw new Error(errorDetail(error, "Cannot load service info"));
      }
      return data;
    },
  });
  if (!info.isSuccess) {
    return null;
  }
  return (
    <Select value={value ?? info.data.default_model} onValueChange={onChange}>
      <SelectTrigger size="sm" aria-label="Model" className="border-none bg-transparent shadow-none">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {info.data.models.map((model) => (
          <SelectItem key={model} value={model}>
            {model}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
