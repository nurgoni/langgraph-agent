# 0003: Frontend React + TypeScript dengan komponen standar

- **Status:** Accepted
- **Tanggal:** 2026-11-15
- **Fitur terkait:** F25, F32–F34, F38, F45

## Konteks

UI v1 adalah Streamlit. Untuk showcase produk dibutuhkan chat UI yang setara aplikasi chat AI
modern, dengan layout seperti Claude: sidebar (chat baru, Projects, Recents), area chat, panel
artifact, dan halaman Project. Pemilik project ingin komponen **standar**, bukan buatan sendiri,
supaya kode frontend mudah dibaca.

## Keputusan

| Lapisan | Pilihan |
|---|---|
| Bahasa | TypeScript (strict) |
| Build dan routing | Vite + React Router |
| Komponen UI | shadcn/ui (Radix + Tailwind) |
| Komponen chat | assistant-ui, dengan runtime custom yang membaca SSE service |
| Data fetching | TanStack Query |
| Tipe API | Digenerate dari kontrak yang dipublikasikan service (F25), tidak ditulis manual |

Aturan kode frontend:

- `frontend/src/components/ui/` (salinan shadcn) diperlakukan sebagai **vendor**: tidak diedit.
  Komponen aplikasi hanya **menyusun** komponen vendor.
- Frontend bicara ke service hanya lewat API native (`/stream`, `/projects`, dan lainnya), bukan
  lewat endpoint OpenAI-compatible, karena Chat Completions tidak bisa membawa reasoning,
  interrupt, sub-agent, dan artifact.
- Monorepo: folder `frontend/` di repo yang sama, supaya perubahan schema dan tipe TS ada di satu
  PR.
- Dijalankan sebagai service `web` di `compose.yaml`.

Streamlit dipertahankan sebagai **dev console** sampai frontend setara fiturnya, lalu dipensiunkan
(backlog B3).

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Next.js | Fitur server (BFF, SSR) belum dibutuhkan karena auth memakai JWT dari service. Dipertimbangkan lagi jika memakai SSO |
| Mantine / MUI (komponen sebagai package) | Tidak ada komponen chat siap pakai, jadi UI chat harus dirakit sendiri |
| Vercel AI SDK `useChat` | Memakai protokol stream sendiri. Adapter untuk reasoning dan sub-agent lebih rumit |
| CopilotKit / AG-UI | Butuh endpoint protokol AG-UI. Dicatat sebagai adapter opsional (backlog B4) |

## Konsekuensi

- Auth per user (F24) dan CORS menjadi prasyarat. `AUTH_SECRET` tidak boleh ada di browser.
- Kontrak API (OpenAPI + JSON Schema event SSE) harus dipublikasikan dan dicek CI (F25).
- Tooling baru di repo: Node.js, pnpm, ESLint, Vitest. CI mendapat job frontend.
- Versi library frontend di-pin, dan API assistant-ui dicek ulang saat F33 dimulai, karena
  library chat AI berubah cepat.
