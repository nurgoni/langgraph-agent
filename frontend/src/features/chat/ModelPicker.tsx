/**
 * Pemilih model di composer (keputusan user F33: model saja, agent ditentukan oleh chat umum atau
 * project). Daftar model dan default service dibaca dari `GET /info`.
 */
import { useServiceInfo } from "@/api/service-info";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface ModelPickerProps {
  /** Model pilihan user, atau `null` untuk default. */
  value: string | null;
  /** Model default chat ini (model project), atau `null` untuk default service. */
  defaultModel?: string | null;
  onChange: (model: string) => void;
}

export function ModelPicker({ value, defaultModel = null, onChange }: ModelPickerProps) {
  const info = useServiceInfo();
  if (!info.isSuccess) {
    return null;
  }
  return (
    <Select value={value ?? defaultModel ?? info.data.default_model} onValueChange={onChange}>
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
