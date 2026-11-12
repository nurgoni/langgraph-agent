# Project Memory

Memori kerja untuk coding agent dan kontributor. Baca sebelum mulai bekerja dan perbarui setelah
ada keputusan penting (lihat Definition of Done di [AGENTS.md](../AGENTS.md)).

**Aturan file ini:**

- Entri Decision Log bersifat append-only, dan entri terbaru ditaruh **paling atas**.
- Entri yang salah tidak dihapus. Tambahkan entri baru yang membatalkannya ("Supersedes: ...").
- Jaga file tetap ringkas (< ~300 baris) karena dimuat otomatis di setiap sesi. Keputusan besar yang
  sudah stabil dipindah ke `docs/adr/`.
- Tanggal ditulis absolut (YYYY-MM-DD).

## Status Saat Ini

- **Fase:** v0.2.0 sudah dirilis. M3 berjalan: F19 sudah di `develop`. F15 selesai di
  `feature/F15-research-assistant`, menunggu push dan PR.
- **Berikutnya:** F16 (interrupt agent), lalu F17 dan rilis v0.3.0.
- **Repo:** remote `origin` = `https://github.com/nurgoni/langgraph-boilerplate-agent.git`.
  Push dari shell agent gagal: belum ada kredensial HTTPS, dan SSH key lokal belum terdaftar di
  GitHub. User yang melakukan push. CLI `gh` tidak terpasang, jadi PR dibuka lewat web.
- **Terakhir diperbarui:** 2026-11-12

## Decision Log

### 2026-11-12: Research assistant dari F15

- **Keputusan:**
  - `ToolCallingAgent(agent_id, description, tools, system_prompt, clock)`. Graph:
    `agent → tools_condition → ToolNode → agent`. `ToolCallingState` menambah `remaining_steps`
    (`RemainingSteps`), dan `MIN_REMAINING_STEPS = 2` menggantikan literal lama.
  - `ToolNode(handle_tool_errors=(ToolException,))`. Tool mengubah error yang diharapkan menjadi
    `ToolException`, sedangkan bug lain tetap terlihat. Default `ToolNode` di langgraph 1.2 hanya
    menangani error validasi argumen.
  - Web search memakai `ddgs` langsung lewat adapter `DuckDuckGoSearch` (`SearchBackend` protocol).
    `DDGS.text` sinkron, jadi dijalankan dengan `asyncio.to_thread`. `DDGS()` tidak membuka
    koneksi saat dibuat.
  - Docstring `@tool` berbahasa Inggris karena dikirim ke LLM (pengecualian dari konvensi
    docstring Indonesia, sama seperti deskripsi `config_schema`).
  - Prompt agent ditulis berbahasa Inggris dengan instruksi "answer in the user's language".
- **Pelajaran:**
  - `DDGS.text(query, **kwargs)` tidak cocok dengan Protocol yang meminta parameter bernama untuk
    pyrefly. Pakai adapter kecil daripada melonggarkan Protocol.
  - Untuk memeriksa input model di test, subclass `FakeModel` yang meng-override `bind_tools`,
    `_generate`, dan `_stream` lalu menyimpan rekaman di `PrivateAttr`.
  - Akses ke index paket kembali normal (`uv add` berhasil). `UV_OFFLINE=1` tetap berguna untuk
    `uv run`/`uv lock` saat jaringan lambat.

### 2026-11-12: Reasoning display dari F19

- **Hasil ukur (langkah 1):** Ollama `qwen3.5:9b` mengirim pemikiran di delta field `reasoning`
  (±200–1900 chunk). Saat model hangat, reasoning pertama datang di detik ~3 dan `content` di
  detik ~10. Cold start menambah ±12 detik untuk memuat model.
- **Keputusan user:** reasoning disimpan di riwayat (open question 5 terjawab).
- **Keputusan desain:**
  - `ReasoningChatOpenAI` (`llm/reasoning.py`) override `_convert_chunk_to_generation_chunk` dan
    `_create_chat_result`. Field `reasoning` dan `reasoning_content` disimpan ke
    `additional_kwargs["reasoning_content"]` (`REASONING_KWARG`). String per chunk digabung
    LangChain, sehingga checkpoint menyimpan reasoning lengkap.
  - `ReasoningEvent` di schema. `StreamService` mengirim reasoning sebelum token dari chunk yang
    sama, dan `stream_tokens=False`/`skip_stream` ikut mematikannya. `ChatMessage.reasoning` diisi
    converter.
  - UI: `MessageRenderer.append_reasoning()` membuka status "Thinking…". Token pertama atau
    message AI menutupnya. Riwayat menampilkan status tertutup, dan `_reasoning_streamed` mencegah
    reasoning digambar dua kali.
  - Test `ReasoningChatOpenAI` memakai `http_client`/`http_async_client` dengan `MockTransport`
    (respons SSE format Ollama), tanpa network.
- **Temuan:** satu smoke test UI time out setelah 300 detik karena model berpikir terlalu lama.
  Ulangan prompt yang sama selesai dalam 51 detik (10.510 karakter reasoning). Rendering UI tidak
  bermasalah (1000 frame dirender dalam 0,2 detik). Belum ada batas token jawaban.

### 2026-11-05: Reasoning model tidak terlihat → fitur F19 (M3)

- **Temuan:** keluhan user "respons lama, terlihat idle" pada `chatbot` dengan `qwen3.5:9b`.
  `chatbot` tidak punya langkah reasoning sendiri, dan UI tidak punya tampilan reasoning. Model
  keluarga Qwen3 berpikir dulu dan (lewat endpoint OpenAI-compatible) mengirim pemikiran di field
  non-standar. `ChatOpenAI` secara eksplisit tidak mengekstrak field non-standar seperti
  `reasoning_content` (peringatan di docstring `langchain-openai`), jadi tidak ada frame selama model
  berpikir. Nama field di Ollama belum diukur karena Ollama mati saat dicek.
- **Keputusan user:** rilis v0.2.0 dulu, lalu tambahkan "reasoning terlihat" sebagai fitur M3
  (F19, FR-29), dikerjakan pertama di M3.
- **Arah desain:** tetap satu jalur OpenAI-compatible (subclass `ChatOpenAI`), event SSE baru
  `reasoning`, dan blok "Thinking" di UI. Penyimpanan reasoning di riwayat masih open question.
- **Pelajaran:** `uv lock` bisa time out saat index paket tidak terjangkau. Untuk perubahan yang
  hanya menyentuh versi project, `uv lock --offline` cukup (resolusi dari cache).

### 2026-11-04: Docker Compose & e2e dari F14

- **Keputusan:**
  - Satu `docker/Dockerfile` dengan target `service` dan `ui` (base yang sama, uv 0.12.18, `uv sync
    --frozen --no-dev --no-editable`), user non-root, SQLite di `/data`, healthcheck Python.
  - `compose.yaml` menulis konfigurasi service secara eksplisit (FakeModel). Hanya `AUTH_SECRET`,
    `LOG_LEVEL`, `SERVICE_PORT`, dan `UI_PORT` yang diambil dari shell atau `.env`.
    `compose.llm.yaml` untuk LLM asli, dengan `DOCKER_LLM_BASE_URL` (interpolasi bertingkat
    `${A:-${B:?}}` didukung Compose v5).
  - Test e2e (`-m integration`) memakai project `agent-service-e2e` dan port acak, dan selalu
    `down -v`. UI diuji dengan `AppTest` di dalam container UI. Job CI `e2e` berjalan setelah job
    `check`.
- **Verifikasi:** streaming token dengan LLM asli lewat `compose.llm.yaml` menghasilkan 7 frame
  token (qwen3.5:9b di host lewat `host.docker.internal`). TODO dari F08/F11 selesai.
- **Utang:** image sekitar 1 GB karena dependency service dan UI belum dipisah (extras). Opsi
  perbaikan: optional-dependencies `service`/`ui`, dengan `uv sync --all-extras` untuk dev dan CI.

### 2026-11-04: Sidebar & URL state dari F13

- **Keputusan user:** `user_id` disimpan di query param URL bersama `thread_id` dan `agent`
  (FR-22 direvisi). Pemegang URL bisa membaca thread tersebut.
- **Keputusan desain:**
  - `AgentClient` per session browser (`st.session_state["agent_client"]`), menggantikan
    `st.cache_resource` dari F12. Supersedes catatan F12 "satu client per konfigurasi".
  - `ChatSession.from_url()` saat session dimulai, dan `session.to_url().write()` di akhir run.
    `user_id` dibuat UI (UUID) jika tidak ada di URL.
  - Aksi sidebar memakai callback `on_click`/`on_change`, bukan `if st.button(): ... st.rerun()`.
  - `ChatView` memanggil `on_thread_created` (menghapus cache daftar thread) dan `st.rerun()`
    setelah thread baru, hanya jika run tanpa error.
  - Toggle streaming = `stream_tokens`. Ganti agent = thread baru.
- **Pelajaran:**
  - `AppTest.query_params` bisa diisi sebelum `run()` dan ikut memantulkan perubahan URL dari
    script.
  - Di `AppTest`, `button.type` adalah tipe elemen. Jenis tombol (`primary`/`secondary`) dibaca dari
    `button.proto.type`.
  - Cache `st.cache_data` bersifat global per proses. Test yang memakai daftar thread perlu memanggil
    `clear_thread_list_cache()` di fixture.
  - Elemen di sidebar dirender sebelum `ChatView` mengirim pesan, jadi perubahan dari pesan baru
    butuh `st.rerun()` agar langsung terlihat di sidebar.

### 2026-11-04: UI chat dari F12

- **Keputusan:**
  - UI memakai `AgentClient` sync (script Streamlit sinkron). Satu client per konfigurasi lewat
    `st.cache_resource`.
  - State percakapan disimpan di dataclass `ChatSession` (`st.session_state["chat_session"]`).
    `thread_id`/`user_id` diambil dari `StreamRun` setelah giliran pertama, dan untuk sementara hanya
    berlaku per session browser.
  - `MessageRenderer` dibuat per pass render. Status tool call dipasangkan lewat `tool_call_id`.
  - Pesan user disimpan ke session hanya setelah service menerima request.
  - Teks UI yang tampil ke user ditulis dalam bahasa Inggris.
- **Pelajaran:**
  - `AppTest.from_file` dan `streamlit run` mengeksekusi script sebagai `__main__`, jadi
    `if __name__ == "__main__": main()` aman dan modul tetap bebas side effect saat di-import
    (doctest).
  - Path relatif di `AppTest.from_file` di-resolve terhadap file pemanggil. Pakai path absolut
    dari `module.__file__`.
  - Untuk test UI, suntikkan `AgentClient` asli dengan `MockTransport` lewat `session_state`,
    karena `AppTest.from_function` tidak bisa membawa closure.

### 2026-11-04: Agent client dari F11

- **Keputusan user:** `invoke` → `AgentReply(message, thread_id, user_id)`. `stream`/`astream` →
  context manager `StreamRun`/`AsyncStreamRun` dengan `thread_id`/`user_id`. Frame `error`
  di-yield sebagai `ErrorEvent`, sedangkan `AgentClientError` hanya untuk HTTP, koneksi, respons
  rusak, atau stream tanpa `[DONE]`.
- **Keputusan desain:**
  - `client/` hanya meng-import `schema/`, httpx, pydantic, dan stdlib (ditegakkan oleh test
    layering). `auth_secret` dan `base_url` diberikan pemanggil. UI (F12) membacanya dari
    `UiSettings`.
  - Request disusun sebagai `RequestSpec` (`client/requests.py`) dan dipakai bersama oleh sync dan
    async. Body selalu dibangun dari schema request, sehingga validasi terjadi di sisi client.
  - `agent_id=None` memakai route agent default. ID di path di-escape (`path_segment`).
- **Supersedes (F02, "`ChatOpenAI` tidak diberi `streaming=True`"):** smoke test dengan LLM asli
  membuktikan bahwa tanpa `streaming=True`, `stream_mode="messages"` hanya menerima satu chunk.
  `ModelFactory` kini memakai `streaming=True`.
- **Pelajaran:**
  - `.env` developer bisa berisi LLM asli (`DEFAULT_MODEL` model asli). Env `USE_FAKE_MODEL=true`
    tidak mengganti model default dari `.env`. Untuk smoke test tanpa LLM, set juga
    `DEFAULT_MODEL=fake`.
  - Smoke test terhadap LLM asli adalah satu-satunya cara menangkap perilaku streaming provider.
    `FakeModel` selalu men-stream.
  - Heredoc bash yang panjang dan berisi banyak backtick kadang gagal di-parse oleh tool shell.
    Tulis script edit ke file scratchpad, lalu jalankan.

### 2026-11-04: SSE streaming dari F08

- **Keputusan:**
  - Route `/stream` menjalankan `build_run_input` sebelum membuat `StreamingResponse`, jadi semua
    error request tetap berupa status HTTP. `StreamService` hanya menangani error di tengah run.
  - `StreamService` memakai stream mode `updates` (message baru + `__interrupt__`), `messages`
    (token), dan `custom` (`get_stream_writer`, berupa dict atau message LangChain).
  - `[DONE]` di-yield setelah `try/except Exception`, **bukan di `finally`**. Yield di dalam
    `finally` saat client putus memicu `RuntimeError` (async generator mengabaikan `GeneratorExit`).
- **Status catatan F02:** jalur token streaming LangGraph `stream_mode="messages"` terbukti memakai
  `_stream` model (dites dengan `FakeModel`). Perilaku `ChatOpenAI` tanpa `streaming=True` belum
  diverifikasi dengan endpoint asli (butuh network). Cek saat test integrasi atau saat smoke test
  F14.
- **Pelajaran:**
  - `ruff format --check .` (dipakai CI) juga memformat blok kode Python di file Markdown, tetapi hook
    pre-commit ruff hanya berjalan untuk file Python. Jalankan `uv run ruff format --check .` setelah
    mengubah contoh kode di dokumen.
  - Package `langchain` (`create_agent`) tidak terpasang. Graph tool-calling di test
  memakai `ToolNode` + `tools_condition` dari `langgraph.prebuilt`.

### 2026-11-04: Rename & delete thread dari F18

- **Keputusan:**
  - Judul custom disimpan di tabel `thread_metadata(thread_id, title)` lewat
    `ThreadMetadataRepository` (`memory/`), sebuah async context manager dengan koneksi
    `aiosqlite` sendiri ke `SQLITE_DB_PATH`. Lifespan membukanya berdampingan dengan
    `CheckpointerProvider`.
  - Koneksi saver tidak dipakai bersama, karena `AsyncSqliteSaver` menjaga transaksinya dengan
    lock privat.
  - Rename/delete ada di `ThreadRepository` (bukan `ThreadService` baru). Kepemilikan dibaca dari
    metadata checkpoint terakhir (`aget_tuple`) lewat `ensure_thread_owner(metadata, ...)`.
  - Delete: `adelete_thread` lalu hapus judul. Setelahnya `/history` → 404, dan ID thread boleh
    dipakai ulang.
  - Listing tetap diurutkan berdasarkan checkpoint terakhir, jadi rename tidak memindahkan thread
    ke atas.

### 2026-11-04: User threads dari F09

- **Keputusan:**
  - `ThreadRepository(checkpointer)` dibuat sekali di lifespan. Listing membaca head checkpoint
    (`step == -1`) dengan filter metadata `user_id` + `agent_id`, mengecek ulang pemilik di setiap
    head, lalu mengurutkan berdasarkan `checkpoint_id` tip (UUID berurutan waktu). Pola dan
    konstanta (`THREAD_HEAD_STEP`, `MAX_THREAD_HEADS`, `HEAD_PAGE_SIZE`, `MAX_HEAD_ROWS`) dari kode
    lama.
  - Paginasi = `limit` saja. Judul fallback `DEFAULT_THREAD_TITLE`.
  - F18 menambah rename/delete ke `ThreadRepository` (atau `ThreadService` di atasnya).
- **Pelajaran:**
  - Sudah diverifikasi di langgraph 1.2/checkpoint 4.3: checkpoint input tiap thread ber-`step -1`
    dan membawa metadata run. `AsyncSqliteSaver.alist(None, filter=...)` mengurutkan lintas thread
    berdasarkan `checkpoint_id` menurun.
  - Test listing memakai `CheckpointerProvider` SQLite asli di `tmp_path`, karena urutan dan filter
    `InMemorySaver` tidak identik dengan SQLite.
  - Saat user bilang F sebelumnya sudah di-merge tapi `origin/develop` belum berisi commit-nya,
    jalankan `git fetch origin` sendiri sebelum membuat branch.

### 2026-11-03: Invoke & history dari F07

- **Keputusan user:**
  - ID thread/user dikembalikan lewat header `X-Thread-Id`/`X-User-Id` (`schema/headers.py`).
    `/stream` (F08) dan client (F11) memakai header yang sama.
  - Kepemilikan thread juga dicek di `/invoke` (dan nanti `/stream`): thread yang sudah ada milik
    user/agent lain → 404 (FR-28). Client wajib mengirim `user_id` yang sama untuk melanjutkan
    thread.
- **Keputusan desain:**
  - Setiap run menyimpan `run_metadata(user_id, agent_id)` di `RunnableConfig["metadata"]`.
    LangGraph menyalinnya ke metadata checkpoint, dan `ensure_thread_owner` membacanya.
    `snapshot.metadata is None` berarti thread baru. F09/F18 memakai metadata yang sama.
  - `build_run_input` adalah function. Config agent yang tidak valid → `RequestValidationError`
    dengan `loc` `body.agent_config.*`.
  - Route punya dua varian, `/{agent_id}/x` dan `/x` (agent default), yang memanggil satu helper.
- **Pelajaran:**
  - Reducer `add_messages` mengisi `id` message secara in-place. Model atau node yang mengembalikan
    objek message yang sama berulang kali akan **menimpa** message lama. Selalu kembalikan objek
    baru (`FakeModel` kini memakai `model_copy(deep=True)`).
  - Pre-commit menyimpan sementara perubahan yang belum di-stage, tapi file untracked tetap
    dicek pyrefly. Stage semua file yang dibutuhkan oleh file untracked.
  - Dengan `--import-mode=importlib`, file test tidak bisa saling import. Agent fake bersama
    disediakan lewat fixture di `tests/service/conftest.py`.

### 2026-11-03: Service app dari F06

- **Keputusan user:**
  - Agent default `chatbot`, sebagai konstanta `DEFAULT_AGENT_ID` di `agents/catalog.py`.
  - Error validasi 422 memakai format bawaan FastAPI (list per field). Error domain dan error tak
    terduga tetap `{"detail": str}`. NFR-6 sudah direvisi.
- **Keputusan desain:**
  - `create_app()` tanpa argumen membaca `Settings()` saat dipanggil, bukan saat import. Semua
    resource dibuat di lifespan. `app.state` berisi `settings`, `default_agent_id`,
    `model_factory`, dan `registry`. Route mengaksesnya lewat alias `SettingsDep`, `RegistryDep`,
    dan lainnya di `service/dependencies.py`.
  - Auth dipasang per router di `create_app` (`include_router(..., dependencies=[Depends(
    verify_bearer)])`). `/health` tidak dipasangi auth.
  - Status error dicari lewat MRO exception (`status_code_for`), jadi subclass ikut terpetakan.
    Handler `Exception` → 500 generik adalah batas sistem dan wajib `logger.exception`.
  - `/info` hanya menampilkan agent yang tersedia.
- **Pelajaran:**
  - `ASGITransport` httpx tidak menjalankan lifespan. Test service membungkus client dengan
    `async with app.router.lifespan_context(app)` (lihat `tests/service/conftest.py`).
  - Handler `Exception` di Starlette tetap me-raise ulang setelah mengirim 500. Pakai
    `ASGITransport(raise_app_exceptions=False)` untuk test 500.
  - Pydantic memakai docstring model sebagai `description` di JSON Schema. Model yang menjadi
    `config_schema` agent butuh deskripsi publik eksplisit (bahasa Inggris) lewat
    `json_schema_extra`, kalau tidak docstring internal ikut tampil di `/info`.
  - `@asynccontextmanager` harus memakai `-> AsyncGenerator[...]`, karena pyrefly menandai
    `AsyncIterator` sebagai deprecated.
  - pytest memakai `--import-mode=importlib`, karena `tests/` mirror `src/` tanpa `__init__.py`.

### 2026-11-03: Agent registry dari F05

- **Keputusan:**
  - `AgentRegistry(model_factory, checkpointer)` menyimpan cache graph per `(agent_id, nama model
    final)`. `load_all()` menjalankan `load()` dan meng-compile graph untuk model default. Kegagalan
    di tahap ini menandai agent unavailable. Ini satu-satunya `except Exception` di `agents/`.
  - Node yang butuh model ditulis sebagai **closure** di dalam `build()`, bukan method. Satu
    instance agent membangun graph untuk beberapa model, jadi model tidak bisa disimpan di `self`.
    Ini pengecualian dari aturan "node ber-dependency = method" di AGENTS.md.
  - Node agent bersifat async. Graph dijalankan lewat `ainvoke`/`astream`, karena `invoke` sync
    gagal ("No synchronous function provided").
  - `agents/` tidak meng-import `schema/`. Service (F06) yang mengubah `BaseAgent` menjadi
    `AgentInfo` dengan `config_schema.model_json_schema()`.
- **Pelajaran:** pyrefly menolak `StateGraph(MessagesState)` (`bad-specialization`), karena tidak
  mengenali TypedDict sebagai `TypedDictLike` milik LangGraph. Ini false positive. Pakai
  `# pyrefly: ignore[bad-specialization]` per baris beserta komentar alasannya, jangan ganti
  state menjadi pydantic.

### 2026-11-03: CheckpointerProvider dari F03

- **Keputusan:**
  - `CheckpointerProvider(db_path)` menerima path, bukan `Settings`. Dependency dibuat sesempit
    yang dibutuhkan, selama tidak ada beberapa nilai settings yang terus dioper bersama.
  - Provider membuat folder induk, menjalankan `setup()` saat `__aenter__`, dan menutup koneksi
    di `__aexit__` lewat `AsyncExitStack`. `pop_all()` membuat koneksi langsung ditutup jika
    `setup()` gagal.
  - Store (long-term memory) tidak ada di v1.
- **Alasan:** startup gagal cepat jika path database tidak bisa ditulis, dan request pertama tidak
  menanggung biaya membuat tabel.

### 2026-11-03: Model factory dan FakeModel dari F02

- **Keputusan:**
  - `ModelFactory(settings).create(name | None)` menyimpan cache per instance factory. Nama di luar
    allowlist → `UnknownModelError` (service memetakannya ke 422). Model non-fake tanpa
    `LLM_BASE_URL`/`LLM_API_KEY` → `ModelNotConfiguredError`, bukan diam-diam jatuh ke
    `OPENAI_API_KEY`.
  - `FakeModel` mewarisi `BaseChatModel`. Respons di-script lewat `responses` (string atau
    `AIMessage`, berputar). Saat streaming, teks dipecah per kata dan `tool_calls` dikirim sebagai
    chunk terakhir.
  - `ChatOpenAI` tidak diberi `streaming=True`. LangGraph tetap men-stream token lewat callback
    `stream_mode="messages"`. Cek ulang di F08.
  - Fixture autouse `block_network` (`tests/conftest.py`) menggagalkan koneksi non-loopback di unit
    test.
- **Alasan:** `GenericFakeChatModel` membuang `tool_calls` saat streaming, sehingga tool call di
  agent loop LangGraph tidak pernah muncul. Aturan "tanpa network call" sekarang ditegakkan oleh
  test, bukan hanya oleh review.
- **Pelajaran:** `BaseChatModel.stream()` selalu menambahkan chunk kosong penanda akhir. Test token
  harus menyaring chunk dengan konten kosong.

### 2026-11-03: Kontrak schema dari F04

- **Keputusan:**
  - `ChatHistoryInput` wajib berisi `user_id`. History memakai cek kepemilikan yang sama dengan
    rename/delete (404 untuk thread milik user lain).
  - Field bebas (`agent_config`, `args`, `response_metadata`, `custom_data`, `config_schema`)
    memakai `pydantic.JsonValue`, bukan `Any`.
  - Event SSE dimodelkan sebagai discriminated union pada field `type`. Service (F08) dan client
    (F11) memakai `STREAM_EVENT_ADAPTER` dan `STREAM_DONE_MARKER` yang sama.
  - Konstanta batas (`THREADS_LIMIT_*`, `TITLE_MAX_LENGTH`) tinggal di `schema/requests.py`, karena
    schema tidak boleh import `core/`. Service memakai konstanta ini langsung dari schema.
- **Alasan:** keputusan user (`user_id`) dan aturan layer di AGENTS.md. Aturan layer ditegakkan oleh
  `tests/schema/test_layering.py`.
- **Workflow:** jika fitur berikutnya bergantung pada branch yang belum di-merge (terutama karena
  `pyproject.toml`/`uv.lock`), buat stacked branch, lalu `rebase --onto` setelah induknya
  di-squash merge.

### 2026-11-03: Konvensi dari F01

- **Docstring dan komentar kode berbahasa Indonesia**, mengikuti contoh di AGENTS.md § Langkah 2.
  Identifier, pesan error, pesan log, dan commit message tetap berbahasa Inggris.
- **Nama field `Settings` huruf kecil** (`llm_base_url`). pydantic-settings mencocokkannya dengan
  env var tanpa membedakan besar-kecil huruf, jadi `LLM_BASE_URL` tetap terbaca.
- **`env_ignore_empty=True`**: env var yang kosong dianggap tidak diisi.
- **`default_model` selalu terisi setelah validasi.** Di mode fake, default-nya `FAKE_MODEL_NAME`
  ("fake") dan nama ini otomatis ditambahkan ke allowlist.
- **Logging memakai function `configure_logging`**, bukan class, karena class dengan satu aksi
  tanpa state melanggar aturan praktis di AGENTS.md.
- **Test yang mengubah state global** (root logger, env) wajib memakai fixture yang mengembalikan
  state tersebut. Test `Settings` memanggil `Settings(_env_file=None)` supaya `.env` milik
  developer tidak ikut terbaca.

### 2026-11-01: Konvensi tooling dari F00

- **Keputusan:**
  - Dependency runtime ditambahkan oleh fitur yang pertama kali membutuhkannya (`dependencies = []`
    di F00).
  - Tool dev di-pin sampai minor (`ruff ~=0.17.1`, `pyrefly ~=1.4.0`), karena rilis minor bisa
    mengubah hasil lint/format.
  - Hook pre-commit untuk ruff/pyrefly memakai `uv run` (hook lokal), sehingga versinya sama dengan
    `uv.lock`.
  - pytest berjalan di stage `pre-push`.
  - uv di CI di-pin ke versi yang menulis `uv.lock` (0.12.18).
  - `exclude-newer` memakai tanggal absolut dan dimajukan setiap kali dependency di-refresh.
  - `.gitattributes` memaksa line ending LF, karena git di mesin Windows ini memakai `autocrlf`.
  - Git author di repo ini: `user.name = nurgoni` (config lokal).
- **Alasan:** toolkit lama mengalami drift versi antara hook dan dev dependency (ruff v0.11.9 vs
  0.15). Pytest mengembalikan exit code 5 kalau tidak ada test, jadi setiap commit minimal punya
  smoke test.

### 2026-11-01: Thread rename/delete + validasi `agent_config` per agent masuk v1

- **Keputusan:** tambah FR-25 (rename), FR-26 (delete), dan FR-27 (`config_schema` per agent).
  Rename/delete dikerjakan sebagai fitur baru **F18** (M1). Validasi config dimasukkan ke
  F04/F05/F06/F07. UI-nya masuk F13.
- **Alasan:** jawaban user untuk open question PRD §11 no. 1 dan 3.
- **Catatan desain:** judul custom disimpan di tabel `thread_metadata` (SQLite yang sama), karena
  metadata checkpoint LangGraph tidak dirancang untuk diubah. Akses ke thread milik user lain
  menghasilkan 404 supaya keberadaan thread tidak bocor.

### 2026-11-01: Git lifecycle

- **Keputusan:** Git Flow ringan (`main` + `develop`), branch `feature/Fxx-<slug>`, squash merge
  ke develop, release ke main dengan `--no-ff` + tag annotated, lalu back-merge. Commit message
  memakai Conventional Commits dalam bahasa Inggris, scope = layer (`memory-md` untuk file ini).
- **Alasan:** pilihan user. Squash menjaga develop tetap 1 commit per fitur. Release sengaja
  tidak di-squash supaya histori main dan develop tetap terhubung. Bahasa Inggris dipilih agar
  kompatibel dengan tooling changelog.
- **Detail:** [CONTRIBUTING.md](../CONTRIBUTING.md).

### 2026-11-01: Package `agent_service`, web search DuckDuckGo

- **Keputusan:** nama package `agent_service`. Tool web search memakai DuckDuckGo.
- **Alasan:** pilihan user. DuckDuckGo tidak butuh API key, sama seperti toolkit lama.

### 2026-11-01: Konverter LangChain → ChatMessage ada di `service/`, bukan `schema/`

- **Keputusan:** `langchain_to_chat_message` diletakkan di `service/converters.py` (F07).
- **Alasan:** AGENTS.md melarang `schema/` bergantung pada langchain, supaya client dan UI bisa
  memakai schema tanpa membawa dependency agent.

### 2026-11-01: Lokasi memory.md di `.agents/`

- **Keputusan:** memory disimpan di `.agents/memory.md`, bukan di `.claude/` atau `docs/`.
- **Alasan:** `.claude/` khusus konfigurasi Claude Code, sedangkan `docs/` untuk dokumen manusia
  yang stabil. `.agents/` netral terhadap tool dan berpasangan dengan `AGENTS.md`. Karena folder
  tersembunyi dilewati glob/ripgrep secara default, file ini ditautkan eksplisit dari AGENTS.md dan
  di-import oleh CLAUDE.md.

### 2026-11-01: Class sebagai default, function sebagai pengecualian

- **Keputusan:** komponen dengan state, dependency, atau lifecycle ditulis sebagai class. Function
  hanya untuk node LangGraph murni, `@tool`, transformasi murni, dependency FastAPI/entrypoint,
  dan fixture pytest.
- **Alasan:** preferensi user. Class juga membuat dependency eksplisit dan menghilangkan global
  state, yang merupakan masalah utama kode lama. Detail ada di AGENTS.md § Class vs Function.

### 2026-11-01: Scope v1 dipersempit

- **Keputusan:** v1 berisi FastAPI + SSE, AgentClient + Streamlit, dan multi-agent registry. Hanya
  satu jalur LLM (OpenAI-compatible + FakeModel) dan hanya SQLite.
- **Alasan:** user tidak memilih multi-provider/multi-DB. Kode lama punya 12 provider dan 3 DB,
  sehingga `settings.py` dan `llm.py` membengkak.
- **Dibuang dari v1:** voice, AG-UI, Langfuse, LangSmith feedback, safeguard Groq, Mongo, Postgres.

### 2026-11-01: Research & RAG assistant digabung

- **Keputusan:** satu class `ToolCallingAgent` yang dikonfigurasi lewat daftar tools.
- **Alasan:** `research_assistant.py` dan `rag_assistant.py` di kode lama ~90% identik.

### 2026-11-01: Bahasa & lokasi dokumen

- **Keputusan:** dokumen ditulis dalam Bahasa Indonesia (istilah teknis tetap Inggris).
  AGENTS.md, PRD.md, dan README.md diletakkan di root `langgraph-boilerplate/`.
- **Alasan:** pilihan user. `agent-service-toolkit/` dibiarkan utuh sebagai referensi read-only.

## Pelajaran dari Kode Lama

Path relatif terhadap `agent-service-toolkit/src/`. Gunakan sebagai daftar "jangan diulang" saat
melakukan port.

| Masalah | Lokasi | Solusi di rewrite |
|---|---|---|
| `Settings()` dibuat saat import, raise jika tanpa key | `core/settings.py:262` | Dibuat di lifespan/factory |
| Model dibuat di level modul, pilihan model user diabaikan | `agents/langgraph_supervisor_agent.py:8` | `BaseAgent.build(model, ...)` per request/model |
| `current_date` dihitung saat import (basi) | `agents/research_assistant.py:39` | Dihitung di dalam node |
| Registry berupa dict global | `agents/agents.py:34` | `AgentRegistry` instance di `app.state` |
| Checkpointer ditempel ke graph setelah compile | `service/service.py:112-114` | `graph.compile(checkpointer=...)` |
| `message_generator` ±110 baris, nesting 6+ | `service/service.py:243-353` | `StreamService` dengan method kecil per jenis event |
| Deteksi sub-agent lewat string nama node | `service/service.py:282` | Tag/metadata eksplisit |
| Agent tidak dikenal → `KeyError` → 500 | `service/service.py:217` | `AgentNotFoundError` → 404 |
| Mutable default `data: dict = {}` | `agents/bg_task_agent/task.py:32` | `None` / `default_factory` |
| Chroma dibangun ulang tiap tool call, path hard-coded | `agents/tools.py:60-68` | Dibuat sekali, path dari Settings |
| `match` provider diulang 12 kali | `core/settings.py:178-251` | Satu provider di v1, strategy map di Future |
| Request client dibangun 4 kali | `client/client.py` | Satu method privat `_build_payload` |
| `except Exception` di ±22 lokasi | `service/`, `agents/`, `voice/` | Exception spesifik, catch-all hanya di batas SSE |
| Magic number (`timeout=60`, `ttl=600`, `k=5`, `remaining_steps < 2`) | `core/llm.py:97`, `streamlit_app.py:56`, `agents/research_assistant.py:75` | Konstanta bernama |
| UI widget (`TaskDataStatus`) di package schema | `schema/task_data.py` | Dipindah ke `ui/` |
| `print()` sebagai log | `agents/safeguard.py`, `agents/command_agent.py` | `logging` |
| Streamlit `main()` ±300 baris, `draw_messages` nesting ±7 | `streamlit_app.py:67-525` | Class view per komponen |

## Pola yang Dipertahankan

- **Konstanta bernama** di `service/threads.py:21-32` (`MAX_THREAD_HEADS`, `TITLE_MAX_LENGTH`, dan
  lainnya). Ini contoh yang baik.
- **Kontrak SSE** `{"type": "message"|"token"|"error"}` + `[DONE]`.
- **Lazy loading agent** (`agents/lazy_agent.py`) → menjadi `BaseAgent.load()`.
- **Bentuk schema Pydantic** di `schema/schema.py` (`UserInput`, `ChatMessage`, dan lainnya).
- **Resume interrupt** dengan `Command(resume=...)` jika thread punya pending interrupt.
- **Filter thread per user** dengan pengecekan ulang metadata agar tidak bocor lintas user
  (`service/threads.py`).
- **Toolchain** uv + ruff + pyrefly + pytest, dan `exclude-newer` di uv untuk supply-chain safety.

## Pertanyaan Terbuka

Sinkron dengan [PRD.md §11](../PRD.md#11-open-questions). Saat ini tidak ada pertanyaan terbuka.

## TODO Berikutnya

- [ ] User: push `feature/F15-research-assistant`, lalu buka PR F15 ke `develop`.
- [ ] User: set `develop` sebagai default branch dan aktifkan branch protection, jika belum
      (CONTRIBUTING.md § Setup Awal Repo).
- [ ] Usulkan ke user: batas token jawaban (misalnya `LLM_MAX_TOKENS`), karena model reasoning
      bisa berpikir sangat lama.
- [ ] F16: interrupt agent (`interrupt()` + resume, tanpa rekursi dan tanpa mutasi state).
