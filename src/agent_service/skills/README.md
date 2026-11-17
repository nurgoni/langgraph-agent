# Skill built-in

Satu folder per skill (`builtin/<name>/SKILL.md`), mengikuti spesifikasi
[Agent Skills](https://agentskills.io) dan [ADR 0005](../../../docs/adr/0005-skill-format-and-sources.md).
Folder ini berisi data, bukan kode Python. Skill dimuat saat startup, dan skill yang tidak valid
dilewati dengan peringatan di log.

- `name` sama dengan nama folder: huruf kecil, angka, dan tanda hubung tunggal, maksimal 64 karakter.
- `description` (maksimal 1024 karakter) menentukan kapan model memuat skill, jadi tulis kapan skill
  dipakai, bukan hanya apa isinya.
- File pendukung ditaruh satu tingkat di bawah folder skill (`references/`, `assets/`) dan dimuat
  model lewat `load_skill(name, path)`.
