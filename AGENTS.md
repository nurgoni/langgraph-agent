# AGENTS.md

Panduan kerja untuk semua coding agent (Claude Code, Codex, Cursor, Copilot) maupun manusia yang
menulis kode di repo ini. Baca file ini dan [`.agents/memory.md`](.agents/memory.md) **sebelum**
mulai bekerja.

- Apa yang dibangun dan kenapa → [PRD.md](PRD.md)
- Cara menjalankan project → [README.md](README.md)
- Keputusan, status, dan konteks terakhir → [.agents/memory.md](.agents/memory.md)
- Cara kerja service (lifespan, alur request, menambah agent) → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Daftar fitur dan urutan pengerjaan → [docs/ROADMAP.md](docs/ROADMAP.md)
- Branch, commit, PR, dan release → [CONTRIBUTING.md](CONTRIBUTING.md)

## Ringkasan Project

Rewrite dari `agent-service-toolkit/` (referensi, **jangan diubah**): service agent berbasis
LangGraph yang diekspos lewat FastAPI (invoke + SSE streaming), dengan Python client dan UI
Streamlit.

| Komponen | Teknologi |
|---|---|
| Bahasa | Python 3.12+ |
| Agent | LangGraph, LangChain |
| API | FastAPI + Uvicorn, SSE |
| Persistence | SQLite checkpointer (`langgraph-checkpoint-sqlite`) |
| Client | httpx (sync + async) |
| UI | Streamlit |
| Tooling | uv, ruff, pyrefly, pytest, pre-commit |

## Perintah

```bash
uv sync                                   # install dependency (termasuk dev)
uv run pytest                             # semua test
uv run pytest --cov=src --cov-report=term # test + coverage
uv run ruff check . --fix                 # lint
uv run ruff format .                      # format
uv run pyrefly check                      # type check
uv run python -m agent_service.run_service   # jalankan API di :8080
uv run streamlit run src/agent_service/ui/app.py  # jalankan UI di :8501
```

Sebelum menyatakan pekerjaan selesai, jalankan: `ruff check`, `ruff format --check`,
`pyrefly check`, dan `pytest`. Semua harus hijau.

## Struktur Folder Target

```text
src/agent_service/
├── core/      # Settings, logging, konstanta global
├── llm/       # ModelFactory, FakeModel
├── agents/    # BaseAgent, AgentRegistry, implementasi agent, tools
├── memory/    # CheckpointerProvider (SQLite)
├── schema/    # Pydantic model untuk API (TANPA dependency UI)
├── service/   # FastAPI app, router, StreamService, auth
├── client/    # AgentClient
└── ui/        # Streamlit app dan komponen view
tests/         # mirror struktur src/
```

### Batas dependensi antar layer

Panah berarti "boleh import". Import ke arah sebaliknya **dilarang**.

```text
ui ──► client ──► schema
service ──► agents ──► llm ──► core
service ──► memory ──► core
service ──► schema
```

- `schema/` hanya boleh bergantung pada `pydantic` dan standard library. Tidak boleh import
  `streamlit`, `fastapi`, atau `langgraph`.
- `client/` dan `ui/` tidak boleh import `agents/`, `service/`, atau `llm/`. Keduanya bicara ke
  service hanya lewat HTTP.

## Prosedur Penulisan Kode

Saat menghasilkan kode, ikuti langkah berikut secara berurutan:

1. **Klarifikasi Input/Output**: Tentukan tipe data masuk dan keluar. Jika ambigu, tanyakan ke
   pengguna sebelum menulis kode.
2. **Tulis Signature + Docstring**: Definisikan fungsi/class dengan type hint lengkap dan docstring
   singkat (satu baris ringkasan, parameter, return, exception). Utamakan class dibandingkan
   function (lihat [Class vs Function](#class-vs-function)).
3. **Implementasi Paling Sederhana**: Tulis versi yang paling mudah dibaca, bahkan jika sedikit
   lebih panjang. Jangan optimasi dulu.
4. **Review Mental Zen**: Periksa apakah ada:
   - Nama yang membingungkan → ganti.
   - Nesting > 2 level → refactor.
   - `except` terlalu luas → persempit.
   - Magic number → jadikan konstanta bernama.
5. **Sertakan Contoh Penggunaan**: Berikan satu blok `if __name__ == "__main__":` atau doctest yang
   mendemonstrasikan pemanggilan.

### Penjelasan per langkah

**Langkah 1: Klarifikasi Input/Output.** Tuliskan tipe sebagai type hint atau Pydantic model,
bukan `dict` bebas. Kalau ada lebih dari satu interpretasi yang masuk akal (misalnya "riwayat"
berarti semua message atau hanya message human/ai), **berhenti dan tanyakan**. Jangan menebak.

**Langkah 2: Signature + Docstring.** Format docstring adalah Google-style:

```python
class ThreadTitleBuilder:
    """Membuat judul thread dari message human pertama."""

    def __init__(self, max_length: int = TITLE_MAX_LENGTH) -> None:
        """Inisialisasi builder.

        Args:
            max_length: Panjang maksimum judul, dalam karakter.
        """
        self._max_length = max_length

    def build(self, messages: list[BaseMessage]) -> str:
        """Ambil konten message human pertama, dipotong ke `max_length`.

        Args:
            messages: Daftar message dalam satu thread, urut kronologis.

        Returns:
            Judul thread, atau `DEFAULT_TITLE` jika tidak ada message human.

        Raises:
            TypeError: Jika konten message bukan string.
        """
```

**Langkah 3: Implementasi paling sederhana.** Pilih `for` loop yang jelas daripada comprehension
bertingkat. Pilih beberapa `if` dengan early return daripada ekspresi ternary berantai. Optimasi
hanya jika ada bukti (profil/benchmark), dan catat alasannya di `.agents/memory.md`.

**Langkah 4: Review Mental Zen.** Checklist yang harus lolos sebelum commit:

| Cek | Aturan | Contoh perbaikan |
|---|---|---|
| Nama | Nama menjelaskan *apa*, bukan *bagaimana*. Hindari `data`, `tmp`, `res`, `handle`. | `res` → `chat_message` |
| Nesting | Maksimal 2 level di dalam satu function/method. | Early return, ekstrak method privat |
| `except` | Tangkap exception spesifik. `except Exception` hanya di batas sistem (handler SSE terluar), wajib di-log dengan `logger.exception`. | `except Exception` → `except httpx.HTTPStatusError` |
| Magic number | Semua literal angka/string bermakna jadi konstanta `UPPER_CASE` di modul atau `core/constants.py`. | `k=5` → `RETRIEVER_TOP_K = 5` |
| Panjang | Function/method sekitar ≤ 40 baris. | Pecah menjadi method privat |

**Langkah 5: Contoh penggunaan.** Setiap modul publik punya salah satu dari:

```python
if __name__ == "__main__":
    builder = ThreadTitleBuilder(max_length=20)
    print(builder.build([HumanMessage("Halo, tolong ringkas dokumen ini")]))
```

atau doctest di docstring (`>>> ...`), yang ikut dijalankan pytest via `--doctest-modules`.

## Class vs Function

**Default: class.** Gunakan class untuk komponen yang punya **state, dependency, atau lifecycle**:

- `Settings`, `ModelFactory`, `AgentRegistry`, `BaseAgent` beserta subclass-nya
- `CheckpointerProvider`, `StreamService`, `AgentClient`, view Streamlit

Class membuat dependency eksplisit lewat konstruktor, mudah di-mock di test, dan menghilangkan
kebutuhan global state.

**Pengecualian: function lebih baik** pada kasus berikut. Setiap kali memilih function, alasannya
harus jelas termasuk salah satu kategori ini:

| Kasus | Kenapa function lebih baik |
|---|---|
| **Node LangGraph** murni | LangGraph memanggil node sebagai `callable(state) -> dict`. Function murni bisa dites dengan satu baris (`assert node(state) == {...}`). Membungkusnya dalam class hanya menambah boilerplate tanpa state. Node yang butuh dependency (model, tools) dijadikan **method** pada class agent builder, bukan class terpisah. |
| **Tool LangChain (`@tool`)** | Decorator `@tool` membaca signature dan docstring function untuk membuat schema tool yang dikirim ke LLM. Method instance membuat `self` ikut terbaca dan merusak schema. |
| **Transformasi murni** tanpa state | Contoh: `langchain_to_chat_message(msg) -> ChatMessage`. Class di sini hanya jadi namespace. *"Simple is better than complex."* Modul sudah berfungsi sebagai namespace. |
| **Dependency FastAPI & entrypoint** | `Depends(verify_bearer)` dan `main()` adalah konvensi framework/CLI, dan function adalah bentuk yang diharapkan. |
| **Fixture pytest** | Pytest mendefinisikan fixture sebagai function. |

**Aturan praktis:** jika sebuah class hanya berisi `__init__` + **satu** method publik dan tidak
menyimpan state yang berubah, ubah menjadi function. Sebaliknya, jika beberapa function terus
saling mengoper argumen yang sama (`settings`, `model`, `checkpointer`), satukan ke dalam class.

## Aturan Zen Tambahan

1. **Tidak ada side effect saat import.** Tidak ada `Settings()`, `get_model()`, compile graph, atau
   koneksi DB di level modul. Semua dibuat di factory/lifespan.
   *Kode lama:* `core/settings.py:262`, `agents/langgraph_supervisor_agent.py:8`.
2. **Tidak ada global yang bisa dimutasi.** Dependency di-inject lewat konstruktor atau disimpan di
   `app.state`. Checkpointer diberikan saat `graph.compile(checkpointer=...)`, bukan ditempel
   belakangan. *Kode lama:* `agents/agents.py:34`, `service/service.py:112-114`.
3. **Waktu dan nilai dinamis dihitung saat dipakai**, bukan saat import.
   *Kode lama:* `current_date` di `agents/research_assistant.py:39`.
4. **`logging`, bukan `print`.** Satu logger per modul: `logger = logging.getLogger(__name__)`.
5. **Tidak ada mutable default** (`def f(data: dict = {})`). Gunakan `None` atau
   `field(default_factory=dict)`. *Kode lama:* `agents/bg_task_agent/task.py:32`.
6. **Error HTTP yang tepat.** Agent tidak dikenal → 404, input tidak valid → 422, bukan 500.
   Definisikan exception domain (`AgentNotFoundError`) dan petakan di exception handler.
7. **Resource mahal dibuat sekali** (vector store, HTTP client, LLM client) lalu di-reuse.
   *Kode lama:* `agents/tools.py:60-68` membangun Chroma di setiap tool call.
8. **Explicit is better than implicit.** Jangan bergantung pada pencocokan string nama node
   (`"supervisor" in node`, `service/service.py:282`). Gunakan tag/metadata eksplisit.

## Konvensi

- **Type hint wajib** di semua signature publik dan privat. `Any` hanya dengan komentar alasan.
- **ruff**: line length 100, target py312, rule set `E,F,I,UP,B,SIM`.
- **Komentar**: default tanpa komentar. Tulis komentar hanya untuk menjelaskan *kenapa* sesuatu
  tidak jelas. Docstring tetap wajib (Langkah 2).
- **Penamaan**: class `PascalCase`, function/method `snake_case`, konstanta `UPPER_CASE`,
  privat diawali `_`.
- **Settings**: semua env var dibaca lewat `Settings` (pydantic-settings). Tidak ada
  `os.environ[...]` di luar `core/`.
- **Async**: kode I/O di service bersifat `async`. Jangan memanggil fungsi blocking di event loop.

## Testing

- Setiap class publik punya test di `tests/` dengan struktur yang mirror `src/`.
- LLM dites dengan `FakeModel` dari `llm/`. **Tidak ada network call di unit test.**
- Endpoint dites dengan `httpx.AsyncClient` + `ASGITransport` dan registry berisi agent fake.
- Test integrasi (Docker, API asli) diberi marker `@pytest.mark.integration` dan dilewati secara
  default.
- Target coverage ≥ 80%.

## Git Workflow

Ringkasan. Detail lengkap ada di [CONTRIBUTING.md](CONTRIBUTING.md).

- Strategi: **Git Flow ringan**. `main` berisi rilis, `develop` adalah integrasi dan default
  branch.
- Satu fitur dari ROADMAP = satu branch `feature/Fxx-<slug>` yang dibuat dari `develop`. Contoh:
  `feature/F05-agent-registry`.
- Commit message memakai **Conventional Commits dalam bahasa Inggris**:
  `<type>(<scope>): <subject>`. Subject imperatif, huruf kecil, tanpa titik, ≤ 72 karakter. Body
  menjelaskan *kenapa*. Footer berisi `Refs: Fxx`.
- Commit atomik: satu perubahan logis, test ikut di commit yang sama, setiap commit lolos hook dan
  test. Ikuti **Rencana commit** milik fitur di ROADMAP.
- Jangan pernah memakai `--no-verify`, force-push ke `main`/`develop`, atau commit langsung ke
  branch permanen.
- PR ke `develop` dengan judul = squash title dari ROADMAP, lalu **squash merge**.
- Release per milestone lewat `release/vX.Y.Z` → `main` dengan **`--no-ff`** (bukan squash), tag
  annotated, lalu back-merge ke `develop`.
- Commit atau push hanya dilakukan jika diminta user.

## Definition of Done

- [ ] Prosedur 5 langkah diikuti, dan checklist Review Mental Zen lolos.
- [ ] Lint, format, type check, dan test hijau.
- [ ] Ada contoh penggunaan (`__main__` atau doctest).
- [ ] README diperbarui jika ada perintah/env var/endpoint baru.
- [ ] PRD diperbarui jika requirement berubah.
- [ ] Status fitur di [docs/ROADMAP.md](docs/ROADMAP.md) diperbarui.
- [ ] **`.agents/memory.md` diperbarui** jika ada keputusan desain, perubahan scope, atau pelajaran
      penting (tambahkan entri baru di paling atas Decision Log).
