# Architecture Decision Records

Keputusan arsitektur yang besar dan sudah stabil dicatat di sini, satu file per keputusan.
Keputusan kecil dan pelajaran harian tetap di [`.agents/memory.md`](../../.agents/memory.md).

**Aturan:**

- Nama file `NNNN-<slug>.md`, nomor berurutan, tidak pernah dipakai ulang.
- ADR yang sudah `Accepted` tidak diedit isinya. Keputusan yang berubah ditulis sebagai ADR baru
  dengan `Supersedes: NNNN`, lalu status ADR lama diubah menjadi `Superseded by NNNN`.
- Status: `Proposed` → `Accepted` → (`Superseded` | `Deprecated`).

## Daftar

| No | Judul | Status | Tanggal |
|---|---|---|---|
| [0001](0001-postgres-only.md) | Postgres sebagai satu-satunya database | Accepted | 2026-11-15 |
| [0002](0002-own-harness.md) | Lapisan harness dibangun sendiri di atas LangGraph | Accepted | 2026-11-15 |
| [0003](0003-frontend-stack.md) | Frontend React + TypeScript dengan komponen standar | Accepted | 2026-11-15 |
| [0004](0004-project-as-declarative-agent.md) | Project sebagai agent deklaratif | Accepted | 2026-11-15 |
| [0005](0005-skill-format-and-sources.md) | Format skill `SKILL.md` dan sumber skill bertingkat | Accepted | 2026-11-15 |

## Template

```markdown
# NNNN: <Judul>

- **Status:** Proposed
- **Tanggal:** YYYY-MM-DD
- **Fitur terkait:** Fxx

## Konteks

Masalah dan batasan yang memaksa keputusan ini.

## Keputusan

Apa yang dipilih, dalam kalimat aktif.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|

## Konsekuensi

Apa yang menjadi lebih mudah, apa yang menjadi lebih sulit, dan utang yang sengaja diambil.
```
