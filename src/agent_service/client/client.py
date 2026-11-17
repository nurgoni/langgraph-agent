"""`AgentClient`: akses ke agent service lewat HTTP, dengan method sync dan async (FR-17)."""

import logging
from types import TracebackType
from typing import Final, Self

import httpx
from pydantic import BaseModel, JsonValue

from agent_service.client.requests import (
    AgentReply,
    RequestSpec,
    parse_model,
    path_segment,
    raise_for_status,
    request_error,
    run_thread_id,
)
from agent_service.client.stream import AsyncStreamRun, StreamRun
from agent_service.schema.auth import LoginRequest, TokenResponse
from agent_service.schema.projects import Project, ProjectCreate, ProjectList, ProjectUpdate
from agent_service.schema.requests import (
    THREADS_LIMIT_DEFAULT,
    ChatHistoryInput,
    StreamInput,
    ThreadRenameInput,
    UserInput,
    UserThreadsQuery,
)
from agent_service.schema.responses import (
    ChatHistory,
    ChatMessage,
    ServiceMetadata,
    ThreadSummary,
    UserThreads,
)
from agent_service.schema.skills import SkillDetail, SkillList

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final = "http://localhost:8080"
DEFAULT_TIMEOUT_SECONDS: Final = 60.0
AUTHORIZATION_HEADER: Final = "Authorization"
BEARER_PREFIX: Final = "Bearer "
LOGIN_PATH: Final = "/auth/login"
PROJECTS_PATH: Final = "/projects"
SKILLS_PATH: Final = "/skills"


class AgentClient:
    """Client untuk agent service. Tidak ada request di konstruktor (FR-19).

    `agent_id=None` berarti route agent default (`/invoke`, `/stream`, dan seterusnya). Ganti
    `agent_id` kapan saja untuk berpindah agent. Jika `project_id` diisi, chat dan thread memakai
    route project (`/projects/{project_id}/...`) dan `agent_id` diabaikan, karena agent ditentukan
    project. Semua endpoint selain `/health` dan
    `/auth/login` butuh access token: panggil `login()` atau berikan `access_token`. Satu koneksi
    HTTP dipakai ulang sampai `close()` atau `aclose()`, atau gunakan `with` / `async with`.
    Setiap method sync punya pasangan async berawalan `a` (`invoke` menjadi `ainvoke`, `stream`
    menjadi `astream`).

    >>> client = AgentClient(base_url="http://localhost:8080", agent_id="chatbot")
    >>> client.agent_id, client.project_id
    ('chatbot', None)
    >>> client.close()
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        access_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        project_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Inisialisasi client tanpa menghubungi service.

        Args:
            base_url: URL service (`AGENT_URL`).
            agent_id: Agent tujuan, atau `None` untuk agent default service.
            access_token: Token dari `login()` sebelumnya, misalnya yang disimpan UI.
            timeout: Batas waktu per operasi HTTP, dalam detik.
            project_id: Project tujuan chat dan thread, atau `None` untuk route agent.
            transport: Transport httpx sync, misalnya `httpx.MockTransport` untuk test.
            async_transport: Transport httpx async.
        """
        self.agent_id = agent_id
        self.project_id = project_id
        self._http_client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._async_http_client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=async_transport
        )
        self._info: ServiceMetadata | None = None
        self.set_access_token(access_token)

    @property
    def has_access_token(self) -> bool:
        """Client sudah memegang access token (belum tentu masih berlaku)."""
        return AUTHORIZATION_HEADER in self._http_client.headers

    def set_access_token(self, access_token: str | None) -> None:
        """Pakai token ini untuk request berikutnya, atau hapus token jika `None` (logout)."""
        for http_client in (self._http_client, self._async_http_client):
            if access_token is None:
                http_client.headers.pop(AUTHORIZATION_HEADER, None)
            else:
                http_client.headers[AUTHORIZATION_HEADER] = BEARER_PREFIX + access_token
        self._info = None

    def login(self, username: str, password: str) -> TokenResponse:
        """Tukar username dan password dengan access token, lalu pakai token itu.

        Raises:
            AgentClientError: 401 jika username atau password salah, 422 jika format username
                tidak valid.
        """
        token = parse_model(self._send(self._login_spec(username, password)), TokenResponse)
        self.set_access_token(token.access_token)
        return token

    async def alogin(self, username: str, password: str) -> TokenResponse:
        """Versi async `login`."""
        response = await self._asend(self._login_spec(username, password))
        token = parse_model(response, TokenResponse)
        self.set_access_token(token.access_token)
        return token

    @property
    def base_url(self) -> str:
        """URL service yang dipakai client, misalnya untuk pesan error di UI."""
        return str(self._http_client.base_url).rstrip("/")

    def __enter__(self) -> Self:
        """Pakai client sync dalam blok `with`."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi sync."""
        self.close()

    async def __aenter__(self) -> Self:
        """Pakai client async dalam blok `async with`."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi async."""
        await self.aclose()

    def close(self) -> None:
        """Tutup koneksi HTTP sync."""
        self._http_client.close()

    async def aclose(self) -> None:
        """Tutup koneksi HTTP async."""
        await self._async_http_client.aclose()

    def get_info(self, refresh: bool = False) -> ServiceMetadata:
        """Agent, model, dan nilai default service. Diambil sekali lalu di-cache.

        Args:
            refresh: Ambil ulang dari service walau sudah ada di cache.

        Raises:
            AgentClientError: Request gagal.
        """
        if self._info is None or refresh:
            response = self._send(self._info_spec())
            self._info = parse_model(response, ServiceMetadata)
        return self._info

    def invoke(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
    ) -> AgentReply:
        """Jalankan agent sampai selesai.

        Args:
            message: Pesan user, atau jawaban untuk pertanyaan interrupt.
            model: Model dari allowlist service. `None` berarti model default.
            thread_id: Thread yang dilanjutkan. `None` berarti thread baru.
            agent_config: Opsi agent sesuai `config_schema`-nya di `/info`.

        Returns:
            Jawaban akhir beserta `thread_id` yang dipakai run.

        Raises:
            AgentClientError: Request gagal, misalnya 401 (token), 404 (agent/thread), atau 422
                (input).
        """
        payload = UserInput(
            message=message,
            model=model,
            thread_id=thread_id,
            agent_config=agent_config or {},
        )
        response = self._send(self._invoke_spec(payload))
        return AgentReply(parse_model(response, ChatMessage), thread_id=run_thread_id(response))

    def stream(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
        stream_tokens: bool = True,
    ) -> StreamRun:
        """Siapkan stream SSE. Request dikirim saat masuk `with`.

        Argumen sama dengan `invoke`, ditambah `stream_tokens` untuk frame `token`. Frame `error`
        dari service diteruskan sebagai `ErrorEvent`, bukan exception.

        Returns:
            Context manager yang punya `thread_id` dan bisa di-iterasi untuk event.
        """
        payload = StreamInput(
            message=message,
            model=model,
            thread_id=thread_id,
            agent_config=agent_config or {},
            stream_tokens=stream_tokens,
        )
        return StreamRun(self._http_client, self._stream_spec(payload))

    def get_history(self, thread_id: str) -> ChatHistory:
        """Semua message satu thread milik pemegang token.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain.
        """
        return parse_model(self._send(self._history_spec(thread_id)), ChatHistory)

    def get_threads(self, limit: int = THREADS_LIMIT_DEFAULT) -> UserThreads:
        """Thread milik pemegang token untuk agent ini, yang terakhir di-update lebih dulu.

        Raises:
            AgentClientError: Request gagal.
        """
        return parse_model(self._send(self._threads_spec(limit)), UserThreads)

    def rename_thread(self, thread_id: str, title: str) -> ThreadSummary:
        """Ganti judul thread.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain, 422 jika judul tidak
                valid.
        """
        spec = self._rename_spec(thread_id, title)
        return parse_model(self._send(spec), ThreadSummary)

    def delete_thread(self, thread_id: str) -> None:
        """Hapus thread beserta seluruh riwayatnya.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain.
        """
        self._send(self._delete_spec(thread_id))

    def list_projects(self) -> ProjectList:
        """Project built-in dan milik user (FR-36).

        Raises:
            AgentClientError: Request gagal.
        """
        return parse_model(self._send(RequestSpec("GET", PROJECTS_PATH)), ProjectList)

    def get_project(self, project_id: str) -> Project:
        """Satu project.

        Raises:
            AgentClientError: 404 jika project tidak ada atau milik user lain.
        """
        return parse_model(self._send(RequestSpec("GET", _project_path(project_id))), Project)

    def create_project(self, project: ProjectCreate) -> Project:
        """Buat project milik user.

        Raises:
            AgentClientError: 422 jika agent, model, atau isinya tidak valid.
        """
        spec = RequestSpec("POST", PROJECTS_PATH, json=_json_body(project))
        return parse_model(self._send(spec), Project)

    def update_project(self, project_id: str, changes: ProjectUpdate) -> Project:
        """Ubah field yang diisi di `changes` saja.

        Raises:
            AgentClientError: 403 untuk project built-in, 404 jika milik user lain.
        """
        return parse_model(self._send(_update_project_spec(project_id, changes)), Project)

    def delete_project(self, project_id: str) -> None:
        """Hapus project beserta semua thread di dalamnya.

        Raises:
            AgentClientError: 403 untuk project built-in, 404 jika milik user lain.
        """
        self._send(RequestSpec("DELETE", _project_path(project_id)))

    def list_skills(self) -> SkillList:
        """Skill yang bisa diaktifkan di project (FR-38).

        Raises:
            AgentClientError: Request gagal.
        """
        return parse_model(self._send(RequestSpec("GET", SKILLS_PATH)), SkillList)

    def get_skill(self, skill_id: str) -> SkillDetail:
        """Satu skill beserta isinya. `skill_id` berbentuk `<scope>/<name>`.

        Raises:
            AgentClientError: 404 jika skill tidak dikenal.
        """
        return parse_model(self._send(RequestSpec("GET", _skill_path(skill_id))), SkillDetail)

    async def alist_skills(self) -> SkillList:
        """Versi async `list_skills`."""
        return parse_model(await self._asend(RequestSpec("GET", SKILLS_PATH)), SkillList)

    async def aget_skill(self, skill_id: str) -> SkillDetail:
        """Versi async `get_skill`."""
        response = await self._asend(RequestSpec("GET", _skill_path(skill_id)))
        return parse_model(response, SkillDetail)

    async def alist_projects(self) -> ProjectList:
        """Versi async `list_projects`."""
        return parse_model(await self._asend(RequestSpec("GET", PROJECTS_PATH)), ProjectList)

    async def aget_project(self, project_id: str) -> Project:
        """Versi async `get_project`."""
        response = await self._asend(RequestSpec("GET", _project_path(project_id)))
        return parse_model(response, Project)

    async def acreate_project(self, project: ProjectCreate) -> Project:
        """Versi async `create_project`."""
        spec = RequestSpec("POST", PROJECTS_PATH, json=_json_body(project))
        return parse_model(await self._asend(spec), Project)

    async def aupdate_project(self, project_id: str, changes: ProjectUpdate) -> Project:
        """Versi async `update_project`."""
        response = await self._asend(_update_project_spec(project_id, changes))
        return parse_model(response, Project)

    async def adelete_project(self, project_id: str) -> None:
        """Versi async `delete_project`."""
        await self._asend(RequestSpec("DELETE", _project_path(project_id)))

    async def aget_info(self, refresh: bool = False) -> ServiceMetadata:
        """Versi async `get_info`. Cache dipakai bersama dengan versi sync."""
        if self._info is None or refresh:
            response = await self._asend(self._info_spec())
            self._info = parse_model(response, ServiceMetadata)
        return self._info

    async def ainvoke(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
    ) -> AgentReply:
        """Versi async `invoke`."""
        payload = UserInput(
            message=message,
            model=model,
            thread_id=thread_id,
            agent_config=agent_config or {},
        )
        response = await self._asend(self._invoke_spec(payload))
        return AgentReply(parse_model(response, ChatMessage), thread_id=run_thread_id(response))

    def astream(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
        stream_tokens: bool = True,
    ) -> AsyncStreamRun:
        """Versi async `stream`. Request dikirim saat masuk `async with`."""
        payload = StreamInput(
            message=message,
            model=model,
            thread_id=thread_id,
            agent_config=agent_config or {},
            stream_tokens=stream_tokens,
        )
        return AsyncStreamRun(self._async_http_client, self._stream_spec(payload))

    async def aget_history(self, thread_id: str) -> ChatHistory:
        """Versi async `get_history`."""
        response = await self._asend(self._history_spec(thread_id))
        return parse_model(response, ChatHistory)

    async def aget_threads(self, limit: int = THREADS_LIMIT_DEFAULT) -> UserThreads:
        """Versi async `get_threads`."""
        response = await self._asend(self._threads_spec(limit))
        return parse_model(response, UserThreads)

    async def arename_thread(self, thread_id: str, title: str) -> ThreadSummary:
        """Versi async `rename_thread`."""
        response = await self._asend(self._rename_spec(thread_id, title))
        return parse_model(response, ThreadSummary)

    async def adelete_thread(self, thread_id: str) -> None:
        """Versi async `delete_thread`."""
        await self._asend(self._delete_spec(thread_id))

    def _send(self, spec: RequestSpec) -> httpx.Response:
        """Kirim request sync dan pastikan statusnya 2xx.

        Raises:
            AgentClientError: Koneksi gagal atau status non-2xx.
        """
        logger.debug("%s %s", spec.method, spec.path)
        try:
            response = self._http_client.request(
                spec.method, spec.path, json=spec.json, params=spec.params
            )
        except httpx.RequestError as error:
            raise request_error(error, f"{spec.method} {spec.path}") from error
        raise_for_status(response)
        return response

    async def _asend(self, spec: RequestSpec) -> httpx.Response:
        """Kirim request async dan pastikan statusnya 2xx.

        Raises:
            AgentClientError: Koneksi gagal atau status non-2xx.
        """
        logger.debug("%s %s", spec.method, spec.path)
        try:
            response = await self._async_http_client.request(
                spec.method, spec.path, json=spec.json, params=spec.params
            )
        except httpx.RequestError as error:
            raise request_error(error, f"{spec.method} {spec.path}") from error
        raise_for_status(response)
        return response

    def _agent_path(self, suffix: str) -> str:
        """Path chat/thread: project terpilih, agent terpilih, atau agent default."""
        if self.project_id is not None:
            return _project_path(self.project_id) + suffix
        if self.agent_id is None:
            return suffix
        return f"/{path_segment(self.agent_id)}{suffix}"

    def _info_spec(self) -> RequestSpec:
        """Request `GET /info`."""
        return RequestSpec("GET", "/info")

    def _login_spec(self, username: str, password: str) -> RequestSpec:
        """Request `POST /auth/login`, dengan username divalidasi schema."""
        body = _json_body(LoginRequest(username=username, password=password))
        return RequestSpec("POST", LOGIN_PATH, json=body)

    def _invoke_spec(self, payload: UserInput) -> RequestSpec:
        """Request `POST /{agent_id}/invoke`."""
        return RequestSpec("POST", self._agent_path("/invoke"), json=_json_body(payload))

    def _stream_spec(self, payload: StreamInput) -> RequestSpec:
        """Request `POST /{agent_id}/stream`."""
        return RequestSpec("POST", self._agent_path("/stream"), json=_json_body(payload))

    def _history_spec(self, thread_id: str) -> RequestSpec:
        """Request `POST /{agent_id}/history`."""
        body = _json_body(ChatHistoryInput(thread_id=thread_id))
        return RequestSpec("POST", self._agent_path("/history"), json=body)

    def _threads_spec(self, limit: int) -> RequestSpec:
        """Request `GET /{agent_id}/threads`, dengan `limit` divalidasi schema."""
        query = UserThreadsQuery(limit=limit)
        params: dict[str, str | int] = {"limit": query.limit}
        return RequestSpec("GET", self._agent_path("/threads"), params=params)

    def _rename_spec(self, thread_id: str, title: str) -> RequestSpec:
        """Request `PATCH /{agent_id}/threads/{thread_id}`."""
        body = _json_body(ThreadRenameInput(title=title))
        return RequestSpec("PATCH", self._thread_path(thread_id), json=body)

    def _delete_spec(self, thread_id: str) -> RequestSpec:
        """Request `DELETE /{agent_id}/threads/{thread_id}`."""
        return RequestSpec("DELETE", self._thread_path(thread_id))

    def _thread_path(self, thread_id: str) -> str:
        """Path satu thread milik agent terpilih."""
        return self._agent_path(f"/threads/{path_segment(thread_id)}")


def _project_path(project_id: str) -> str:
    """Path satu project, dengan ID di-escape.

    >>> _project_path("p/1")
    '/projects/p%2F1'
    """
    return f"{PROJECTS_PATH}/{path_segment(project_id)}"


def _skill_path(skill_id: str) -> str:
    """Path satu skill. Scope dan nama di-escape terpisah, karena `/` adalah pemisah ID.

    >>> _skill_path("builtin/meeting-notes")
    '/skills/builtin/meeting-notes'
    """
    segments = [path_segment(segment) for segment in skill_id.split("/")]
    return "/".join([SKILLS_PATH, *segments])


def _update_project_spec(project_id: str, changes: ProjectUpdate) -> RequestSpec:
    """Request `PATCH /projects/{project_id}` berisi field yang diisi saja.

    `model=None` yang diisi eksplisit tetap dikirim, supaya model project bisa dihapus.
    """
    body = changes.model_dump(mode="json", exclude_unset=True)
    return RequestSpec("PATCH", _project_path(project_id), json=body)


def _json_body(payload: BaseModel) -> dict[str, JsonValue]:
    """Body JSON dari schema request, tanpa field yang kosong."""
    return payload.model_dump(mode="json", exclude_none=True)
