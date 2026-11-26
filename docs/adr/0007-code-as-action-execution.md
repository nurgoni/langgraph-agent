# 0007: Code-as-action: kernel per thread, akses data lewat service

- **Status:** Accepted
- **Tanggal:** 2026-11-26
- **Fitur terkait:** F47, F49, F39, F40, F41
- **Supersedes:** sebagian keputusan F37 "satu container per eksekusi" (untuk `run_python`)

## Konteks

Strategi analisa data adalah **code-as-action**: agent diberi primitif yang bisa dikomposisi
(eksplorasi data, query, eksekusi kode), bukan satu fungsi per skenario. Agar strategi ini bekerja,
tiga syarat harus dipenuhi:

1. **Iteratif.** Agent membangun analisa langkah demi langkah. F37 menjalankan setiap `run_python`
   di container baru, sehingga variabel, import, dan DataFrame hilang di setiap langkah. Model
   harus menulis ulang script lengkap dan membaca ulang data.
2. **Memperbaiki diri dengan batas.** Error sudah dikembalikan sebagai observasi (exit code, stderr,
   timeout). Tetapi tidak ada batas retry, dan `recursion_limit` memakai default LangGraph (10.007),
   jadi model yang terus gagal bisa mencoba ulang ribuan kali. Ini berbahaya untuk job terjadwal
   (F41) yang berjalan tanpa user.
3. **Aman terhadap data.** Kode buatan model tidak boleh bisa mengubah atau membocorkan data.

## Keputusan

**Kernel per thread (F49).** `run_python` dijalankan di kernel Python berumur panjang per thread,
dikelola `sandbox-runner`:

- Variabel dan import bertahan antar pemanggilan di thread yang sama.
- Isolasi sama dengan F37: tanpa jaringan, rootfs read-only, non-root, tanpa capability, batas
  memori/CPU/proses, dan timeout per eksekusi.
- **Workspace tetap sumber kebenaran.** Kernel boleh mati (TTL idle, batas jumlah kernel aktif,
  crash, restart runner). Saat kernel baru dibuat, model diberi tahu bahwa state memori hilang dan
  file workspace tetap ada.
- `run_shell` tetap sekali pakai (container per pemanggilan), karena perintah shell jarang butuh
  state.

**Batas langkah dan retry (F47)**, berlaku untuk semua agent:

- `recursion_limit` eksplisit di config setiap run, bukan default LangGraph.
- Kegagalan beruntun pada **tool yang sama** dihitung. Setelah 3 kali (`TOOL_MAX_CONSECUTIVE_ERRORS`),
  tool itu menolak dijalankan lagi di giliran tersebut, dan model diminta menjelaskan error ke
  user. Kegagalan mencakup `ToolException`, dan untuk tool eksekusi juga exit code bukan nol atau
  timeout.

**Akses database hanya lewat service.** Sandbox dan kernel tetap **tanpa jaringan** dan tidak
pernah menerima kredensial database. Query dijalankan tool `run_sql` di proses service dengan user
database read-only, `sqlglot` (hanya satu `SELECT`), batas baris, dan `statement_timeout`. Hasil
query masuk workspace (Parquet), lalu dimuat ke kernel oleh kode model.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Tetap satu container per eksekusi | Agent tidak bisa iteratif, dan biaya per langkah tinggi (start container, salin workspace, impor ulang) |
| Kernel di proses service | Melanggar NFR-10: kode model tidak pernah berjalan di proses service |
| Sandbox dengan kredensial database read-only | Butuh jaringan dari sandbox ke database, dan kode model memegang kredensial. Read-only tidak mencegah query berat atau pembacaan tabel yang tidak dimaksud. Akses lewat service sudah memenuhi kebutuhan iteratif |
| MicroVM (Firecracker, gVisor) sekarang | Tetap backlog B5 (sandbox production). Container + hardening cukup untuk dev dan demo |
| Retry tanpa batas, hanya mengandalkan prompt | Model kecil tidak patuh secara konsisten. Batas harus ditegakkan harness |

## Konsekuensi

- `sandbox-runner` menjadi **stateful**: menyimpan peta thread → kernel. Satu replika runner, atau
  routing berdasarkan thread jika nanti di-scale.
- Resource dipakai per thread aktif. TTL idle dan batas kernel aktif wajib, dan kernel tertua yang
  idle dihentikan lebih dulu saat batas tercapai.
- Penghapusan thread juga menghentikan kernel-nya (`ThreadDataCleanup`).
- Playbook dan eval F40 ditulis untuk pola iteratif, bukan script lengkap per langkah.
- Job terjadwal (F41) terlindungi oleh F47 dan tidak bisa berputar tanpa batas.
