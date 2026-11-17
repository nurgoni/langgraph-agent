---
name: memory-maintenance
description: Memperbarui .agents/memory.md di repo ini, yaitu menulis entri Decision Log setelah fitur atau keputusan, memperbarui Status, dan mengarsipkan entri milestone lama saat file melewati ±300 baris. Pakai di akhir setiap fitur atau rilis, saat user membuat keputusan desain, atau saat memory.md terlalu panjang.
---

# Memory maintenance

`.agents/memory.md` dimuat di setiap sesi (CLAUDE.md meng-import-nya), jadi setiap baris memakan
konteks. Tulis yang tidak bisa diturunkan dari kode, git, atau dokumen lain.

## Entri Decision Log

Taruh **paling atas** di § Decision Log. Format:

```markdown
### YYYY-MM-DD: <topik> dari Fxx

- **Keputusan user:** jawaban Langkah 1, singkat.
- **Keputusan desain:** pilihan yang tidak terlihat jelas dari kode (lokasi modul, kontrak, batas,
  alasan menolak alternatif). Jangan menyalin isi kode.
- **Hasil ukur:** angka dari smoke test atau probe (model, latensi, token), jika ada.
- **Pelajaran:** jebakan yang menghabiskan waktu dan akan terulang (library, Windows, tooling).
```

- Append-only: entri lama tidak diedit. Keputusan yang berubah ditulis sebagai entri baru dengan
  `**Supersedes:** <entri lama>`.
- Pelajaran yang berlaku lintas fitur dan akan terulang juga diringkas satu baris di
  § Pelajaran Lintas Fitur. Aturan dari user yang berlaku untuk semua pekerjaan masuk
  § Aturan Kerja.
- Tanggal absolut. Nama file dan simbol ditulis dengan backtick, supaya mudah di-grep.

## Status Saat Ini

Selalu perbarui: fase, apa yang menunggu user (commit/PR/rilis), fitur berikutnya, dan
`Terakhir diperbarui: YYYY-MM-DD (<konteks>)`. Sinkronkan § Pertanyaan Terbuka dengan PRD §11,
dan coret TODO yang selesai.

## Arsip saat > ±300 baris

Cek dengan `wc -l .agents/memory.md`. Jika melewati ±300 baris:

1. Pilih entri milestone yang **sudah dirilis** dan tidak sedang dikerjakan. Entri rencana yang
   masih mengarahkan pekerjaan (misalnya "Rencana Fase 2") tetap di memory.md.
2. Pindahkan entri itu **utuh** (tanpa diedit) ke `.agents/archive/decision-log-<rentang>.md`,
   dengan header yang menjelaskan asal dan tanggal pemindahan. Contoh:
   `.agents/archive/decision-log-m0-m4.md`. Pindahkan lewat script yang memotong berdasarkan judul
   `### `, bukan dengan menyalin ulang teks.
3. Pastikan pelajaran yang masih berlaku dari entri itu sudah ada di § Pelajaran Lintas Fitur,
   dan aturan user di § Aturan Kerja.
4. Tambahkan atau perbarui tautan arsip di § Status.
5. Keputusan arsitektur besar yang stabil sebaiknya menjadi ADR di `docs/adr/`.
