"""Hasil query sebagai Parquet untuk workspace (FR-51, ADR 0007).

Hasil `run_sql` disimpan sebagai Parquet supaya kode di sandbox (dan kernel F49) bisa memuatnya
dengan tipe yang benar, tanpa kredensial database. Kolom yang tipenya tidak dikenal Arrow (UUID,
JSON campuran) disimpan sebagai teks.
"""

import io
from collections.abc import Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from agent_service.datasource.model import QueryResult

ARROW_CONVERSION_ERRORS = (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError)


def to_parquet(result: QueryResult) -> bytes:
    """Ubah hasil query menjadi isi file Parquet.

    Function, bukan class: transformasi murni. Blocking (CPU), jadi panggil lewat
    `asyncio.to_thread` dari kode async.

    >>> from datetime import date
    >>> content = to_parquet(QueryResult(["day", "n"], ["date", "int8"], [(date(2026, 1, 1), 3)]))
    >>> pq.read_table(io.BytesIO(content)).to_pylist()
    [{'day': datetime.date(2026, 1, 1), 'n': 3}]
    """
    columns: dict[str, pa.Array] = {}
    for index, name in enumerate(_unique_names(result.columns)):
        columns[name] = _column_array([row[index] for row in result.rows])
    buffer = io.BytesIO()
    pq.write_table(pa.table(columns), buffer)
    return buffer.getvalue()


def _column_array(values: Sequence[object]) -> pa.Array:
    """Array Arrow dengan tipe yang ditebak, atau teks jika tipe nilainya tidak didukung."""
    try:
        return pa.array(values)
    except ARROW_CONVERSION_ERRORS:
        return pa.array([None if value is None else str(value) for value in values])


def _unique_names(columns: Sequence[str]) -> list[str]:
    """Nama kolom unik, karena SQL boleh menghasilkan nama sama (`count`, `count`).

    >>> _unique_names(["count", "count", "region"])
    ['count', 'count_2', 'region']
    """
    names: list[str] = []
    for name in columns:
        candidate = name
        suffix = 2
        while candidate in names:
            candidate = f"{name}_{suffix}"
            suffix += 1
        names.append(candidate)
    return names
