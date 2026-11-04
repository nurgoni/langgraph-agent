"""Daftar thread milik user, dibaca langsung dari metadata checkpoint (FR-9).

Thread tidak punya tabel sendiri. Setiap run menyimpan `user_id` dan `agent_id` di metadata
checkpoint (lihat `thread_access.run_metadata`), jadi listing cukup membaca checkpoint dengan
filter metadata tersebut. Invariant yang dipakai dijelaskan di konstanta berikut.
"""

import logging
from collections.abc import Iterable
from typing import Final

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointTuple

from agent_service.agents.base import Checkpointer
from agent_service.memory.thread_metadata import ThreadMetadataRepository
from agent_service.schema.requests import TITLE_MAX_LENGTH
from agent_service.schema.responses import ThreadSummary
from agent_service.service.converters import MESSAGES_KEY, content_to_text
from agent_service.service.thread_access import (
    AGENT_ID_METADATA_KEY,
    USER_ID_METADATA_KEY,
    ThreadNotFoundError,
    ensure_thread_owner,
    is_thread_owner,
)

logger = logging.getLogger(__name__)

# LangGraph menulis checkpoint input dengan step -1 tepat sekali per thread, di run pertamanya.
# Jangan ganti ke step lain: thread dengan satu giliran tidak pernah mencapai step besar.
THREAD_HEAD_STEP: Final = -1
STEP_METADATA_KEY: Final = "step"

# Head diurutkan dari thread terbaru dibuat, sehingga daftar diambil berlebih lalu diurutkan ulang
# berdasarkan update terakhir. Thread yang lebih tua dari head terakhir yang diambil tidak tampil.
MAX_THREAD_HEADS: Final = 200
HEAD_PAGE_SIZE: Final = 200

# Satu baris head belum tentu satu thread unik: agent dengan subgraph menulis head per panggilan
# subgraph dengan metadata induk. Konstanta ini membatasi paging yang mengompensasinya.
MAX_HEAD_ROWS: Final = 1000

DEFAULT_THREAD_TITLE: Final = "Untitled thread"


class ThreadRepository:
    """Operasi thread milik user: daftar, rename, dan hapus.

    Dibuat sekali di lifespan. Checkpoint menjadi sumber kepemilikan dan isi thread, sedangkan
    judul custom dibaca dari `ThreadMetadataRepository`.
    """

    def __init__(
        self,
        checkpointer: Checkpointer,
        titles: ThreadMetadataRepository,
        page_size: int = HEAD_PAGE_SIZE,
        max_threads: int = MAX_THREAD_HEADS,
        max_rows: int = MAX_HEAD_ROWS,
    ) -> None:
        """Inisialisasi repository.

        Args:
            checkpointer: Saver yang sama dengan yang dipakai graph agent.
            titles: Penyimpanan judul custom thread.
            page_size: Jumlah head per query ke checkpointer.
            max_threads: Batas thread unik yang dipertimbangkan sebelum diurutkan.
            max_rows: Batas total baris head yang dibaca.
        """
        self._checkpointer = checkpointer
        self._titles = titles
        self._page_size = page_size
        self._max_threads = max_threads
        self._max_rows = max_rows

    async def list_threads(self, user_id: str, agent_id: str, limit: int) -> list[ThreadSummary]:
        """Daftar thread milik user untuk satu agent, yang terakhir di-update lebih dulu.

        Args:
            user_id: Pemilik thread.
            agent_id: Agent yang menjalankan thread.
            limit: Jumlah maksimum thread yang dikembalikan.

        Returns:
            Ringkasan thread (judul dari message human pertama, waktu update terakhir).
        """
        ranked: list[tuple[str, ThreadSummary]] = []
        for thread_id in await self._list_thread_ids(user_id, agent_id):
            tip = await self._checkpointer.aget_tuple(
                RunnableConfig(configurable={"thread_id": thread_id})
            )
            if tip is None:
                continue
            ranked.append((_checkpoint_id(tip), _summarize(tip, agent_id)))
        # checkpoint_id adalah UUID berurutan waktu, jadi ID tip mengurutkan update terakhir.
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [summary for _, summary in ranked[:limit]]

    async def rename(
        self, thread_id: str, user_id: str, agent_id: str, title: str
    ) -> ThreadSummary:
        """Ganti judul thread dengan judul custom (FR-25).

        Args:
            thread_id: Thread yang di-rename.
            user_id: User yang meminta, harus pemilik thread.
            agent_id: Agent di URL, harus agent yang menjalankan thread.
            title: Judul baru yang sudah divalidasi schema.

        Returns:
            Ringkasan thread dengan judul baru.

        Raises:
            ThreadNotFoundError: Thread tidak ada, atau milik user/agent lain (404).
        """
        tip = await self._get_owned_tip(thread_id, user_id, agent_id)
        await self._titles.set_title(thread_id, title)
        return _summarize(tip, agent_id, custom_title=title)

    async def delete(self, thread_id: str, user_id: str, agent_id: str) -> None:
        """Hapus semua checkpoint thread beserta judul custom-nya (FR-26).

        Args:
            thread_id: Thread yang dihapus.
            user_id: User yang meminta, harus pemilik thread.
            agent_id: Agent di URL, harus agent yang menjalankan thread.

        Raises:
            ThreadNotFoundError: Thread tidak ada, atau milik user/agent lain (404).
        """
        await self._get_owned_tip(thread_id, user_id, agent_id)
        await self._checkpointer.adelete_thread(thread_id)
        await self._titles.delete(thread_id)
        logger.info("Deleted thread %s for agent %s", thread_id, agent_id)

    async def _get_owned_tip(self, thread_id: str, user_id: str, agent_id: str) -> CheckpointTuple:
        """Checkpoint terakhir thread, setelah memastikan pemiliknya.

        Raises:
            ThreadNotFoundError: Thread tidak ada, atau milik user/agent lain.
        """
        tip = await self._checkpointer.aget_tuple(
            RunnableConfig(configurable={"thread_id": thread_id})
        )
        if tip is None:
            raise ThreadNotFoundError(thread_id)
        ensure_thread_owner(tip.metadata, thread_id, user_id, agent_id)
        return tip

    async def _list_thread_ids(self, user_id: str, agent_id: str) -> list[str]:
        """Kumpulkan ID thread dari head checkpoint, dari thread terbaru dibuat."""
        metadata_filter = {
            USER_ID_METADATA_KEY: user_id,
            AGENT_ID_METADATA_KEY: agent_id,
            STEP_METADATA_KEY: THREAD_HEAD_STEP,
        }
        thread_ids: list[str] = []
        rows_scanned = 0
        before: RunnableConfig | None = None
        while len(thread_ids) < self._max_threads and rows_scanned < self._max_rows:
            page = [
                head
                async for head in self._checkpointer.alist(
                    None, filter=metadata_filter, before=before, limit=self._page_size
                )
            ]
            rows_scanned += len(page)
            self._collect_owned_thread_ids(page, user_id, agent_id, thread_ids)
            if len(page) < self._page_size:
                break
            before = RunnableConfig(configurable={"checkpoint_id": _checkpoint_id(page[-1])})
        return thread_ids[: self._max_threads]

    @staticmethod
    def _collect_owned_thread_ids(
        heads: Iterable[CheckpointTuple], user_id: str, agent_id: str, thread_ids: list[str]
    ) -> None:
        """Tambahkan ID thread baru ke `thread_ids`, dengan cek ulang pemilik di setiap head.

        Filter checkpointer seharusnya sudah benar. Cek ulang ini mencegah thread bocor lintas
        user jika implementasi saver mengabaikan filter.
        """
        for head in heads:
            thread_id = head.config["configurable"]["thread_id"]
            if thread_id in thread_ids:
                continue
            if is_thread_owner(head.metadata, user_id, agent_id):
                thread_ids.append(thread_id)
            else:
                logger.warning("Skipping thread %s: checkpointer ignored owner filter", thread_id)


def _checkpoint_id(checkpoint: CheckpointTuple) -> str:
    """ID checkpoint dari config-nya."""
    return checkpoint.config["configurable"]["checkpoint_id"]


def _summarize(
    tip: CheckpointTuple, agent_id: str, custom_title: str | None = None
) -> ThreadSummary:
    """Ringkas checkpoint terakhir thread. Judul custom menimpa judul dari message human."""
    messages = tip.checkpoint["channel_values"].get(MESSAGES_KEY, [])
    title = thread_title(messages) if custom_title is None else custom_title
    return ThreadSummary(
        thread_id=tip.config["configurable"]["thread_id"],
        agent_id=agent_id,
        title=title,
        updated_at=tip.checkpoint["ts"],
    )


def thread_title(messages: Iterable[object]) -> str:
    """Judul thread: message human pertama, dipotong ke `TITLE_MAX_LENGTH`.

    >>> thread_title([HumanMessage("Tolong ringkas dokumen ini")])
    'Tolong ringkas dokumen ini'
    >>> thread_title([])
    'Untitled thread'
    """
    for message in messages:
        if isinstance(message, HumanMessage):
            return content_to_text(message.content)[:TITLE_MAX_LENGTH]
    return DEFAULT_THREAD_TITLE
