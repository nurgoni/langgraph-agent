"""Nama header HTTP yang menjadi bagian kontrak API, dipakai bersama oleh service dan client.

Response `/invoke` dan `/stream` membawa ID thread yang dipakai run, termasuk ID yang baru dibuat
service karena request tidak mengirimnya (FR-13). Identitas user diambil dari access token, jadi
tidak ada header ID user.

>>> THREAD_ID_HEADER
'X-Thread-Id'
"""

from typing import Final

THREAD_ID_HEADER: Final = "X-Thread-Id"
