"""Nama header HTTP yang menjadi bagian kontrak API, dipakai bersama oleh service dan client.

Response `/invoke` dan `/stream` membawa ID thread dan user yang dipakai run, termasuk ID yang
baru dibuat service karena request tidak mengirimnya (FR-13).

>>> THREAD_ID_HEADER, USER_ID_HEADER
('X-Thread-Id', 'X-User-Id')
"""

from typing import Final

THREAD_ID_HEADER: Final = "X-Thread-Id"
USER_ID_HEADER: Final = "X-User-Id"
