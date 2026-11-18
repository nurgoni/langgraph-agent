"""Eksekusi kode buatan model di container terisolasi (FR-49, NFR-10, F37).

Kode model tidak pernah dijalankan di proses service. Agent-service memanggil `Sandbox`
(`RemoteSandbox` ke service `sandbox-runner`), dan hanya runner yang memegang akses Docker
(`DockerSandbox`). Hanya boleh meng-import `core/`, Pydantic, httpx, dan FastAPI (untuk runner).
"""
