"""`WorkspaceToolkit`: tool file, offloader output tool, dan catatan lampiran (FR-47, FR-48, F36).

Satu objek dipakai `ToolCallingAgent` untuk tiga hal: tool file yang di-bind ke model, wrapper
`ToolNode` yang memindahkan output besar ke workspace, dan catatan path lampiran di pesan human.
Catatan lampiran hanya ditambahkan ke salinan message yang dikirim ke model, jadi riwayat yang
dilihat user tidak berubah.
"""

from collections.abc import Sequence
from typing import Final

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agent_service.core.constants import WORKSPACE_FILES_KWARG
from agent_service.harness.context_policy import CHARS_PER_TOKEN
from agent_service.harness.offload import ToolOutputOffloader
from agent_service.harness.tools.files import create_workspace_tools

ATTACHMENT_NOTE_HEADING: Final = "[Attached files in the workspace (read them with read_file):"


class WorkspaceToolkit:
    """Tool file workspace dan pembatas output tool untuk satu agent.

    Workspace sendiri tidak disimpan di sini: tool membacanya dari runtime context setiap run.
    """

    def __init__(self, output_max_tokens: int) -> None:
        """Inisialisasi toolkit.

        Args:
            output_max_tokens: Batas output satu tool call (`TOOL_OUTPUT_MAX_TOKENS`).
        """
        self._tools = create_workspace_tools(output_max_tokens * CHARS_PER_TOKEN)
        self._offloader = ToolOutputOffloader(output_max_tokens)

    @property
    def tools(self) -> list[BaseTool]:
        """Tool file yang selalu di-bind ke model (keputusan user F36)."""
        return list(self._tools)

    @property
    def offloader(self) -> ToolOutputOffloader:
        """Wrapper `awrap_tool_call` untuk `ToolNode` agent."""
        return self._offloader


def with_attachment_notes(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Salinan `messages` dengan path lampiran ditambahkan ke isi pesan human yang membawanya.

    >>> human = HumanMessage("Summarize", additional_kwargs={"workspace_files": ["uploads/a.csv"]})
    >>> print(with_attachment_notes([human])[0].content)
    Summarize
    <BLANKLINE>
    [Attached files in the workspace (read them with read_file):
    - uploads/a.csv]
    """
    noted: list[BaseMessage] = []
    for message in messages:
        paths = _attachment_paths(message)
        if not paths or not isinstance(message.content, str):
            noted.append(message)
            continue
        listing = "\n".join(f"- {path}" for path in paths)
        note = f"{ATTACHMENT_NOTE_HEADING}\n{listing}]"
        noted.append(message.model_copy(update={"content": f"{message.content}\n\n{note}"}))
    return noted


def _attachment_paths(message: BaseMessage) -> list[str]:
    """Path lampiran di `additional_kwargs[WORKSPACE_FILES_KWARG]`, khusus pesan human."""
    if not isinstance(message, HumanMessage):
        return []
    value = message.additional_kwargs.get(WORKSPACE_FILES_KWARG)
    if not isinstance(value, list):
        return []
    return [path for path in value if isinstance(path, str)]
