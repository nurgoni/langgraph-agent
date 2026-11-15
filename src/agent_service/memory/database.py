"""Engine SQLAlchemy async ke Postgres, dibuat sekali per proses (ADR 0001).

SQLAlchemy dan checkpointer LangGraph memakai driver yang sama (psycopg 3), jadi `DATABASE_URL`
cukup ditulis sebagai `postgresql://...`. Modul ini menambahkan nama driver untuk SQLAlchemy.
"""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Final

from sqlalchemy import URL, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

SQLALCHEMY_DRIVER: Final = "postgresql+psycopg"
DB_POOL_SIZE: Final = 5
DB_MAX_OVERFLOW: Final = 5
# Tanpa batas, psycopg menunggu 130 detik. Di Windows, koneksi yang ditolak pun baru terdeteksi
# setelah timeout ini, jadi startup dengan database mati akan menggantung lebih dari 2 menit.
DB_CONNECT_TIMEOUT_SECONDS: Final = 5
CONNECTION_CHECK_SQL: Final = "SELECT 1"
START_DATABASE_HINT: Final = "Start it with `docker compose up -d postgres`."


class DatabaseUnavailableError(RuntimeError):
    """Postgres di `DATABASE_URL` tidak bisa dihubungi saat startup."""


class DatabaseAlreadyOpenError(RuntimeError):
    """`DatabaseEngineProvider` dibuka lagi sebelum ditutup."""


def sqlalchemy_url(database_url: str) -> URL:
    """Ubah `DATABASE_URL` menjadi URL SQLAlchemy dengan driver psycopg.

    >>> url = sqlalchemy_url("postgresql://agent:secret@localhost:5432/agent_service")
    >>> url.render_as_string(hide_password=False)
    'postgresql+psycopg://agent:secret@localhost:5432/agent_service'
    """
    return make_url(database_url).set(drivername=SQLALCHEMY_DRIVER)


def describe_database(database_url: str) -> str:
    """Alamat database tanpa password, untuk pesan error dan log.

    >>> describe_database("postgresql://agent:secret@db:5432/agent_service")
    'db:5432/agent_service'
    """
    url = make_url(database_url)
    return f"{url.host}:{url.port}/{url.database}"


def create_database_engine(
    database_url: str, connect_timeout: int = DB_CONNECT_TIMEOUT_SECONDS
) -> AsyncEngine:
    """Buat engine async dengan pool koneksi. Koneksi baru dibuka saat pertama dipakai.

    Args:
        database_url: URL Postgres (`DATABASE_URL`).
        connect_timeout: Batas waktu membuka satu koneksi, dalam detik.

    >>> engine = create_database_engine("postgresql://agent:secret@localhost:5432/agent_service")
    >>> engine.url.drivername
    'postgresql+psycopg'
    """
    return create_async_engine(
        sqlalchemy_url(database_url),
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout},
    )


class DatabaseEngineProvider:
    """Async context manager yang membuat engine, memastikan Postgres terjangkau, lalu menutupnya.

    Startup gagal cepat dengan pesan yang jelas jika database mati, bukan saat request pertama.

    Contoh di lifespan::

        async with DatabaseEngineProvider(database_url) as engine:
            titles = ThreadMetadataRepository(engine)
    """

    def __init__(
        self, database_url: str, connect_timeout: int = DB_CONNECT_TIMEOUT_SECONDS
    ) -> None:
        """Inisialisasi provider tanpa membuka koneksi.

        Args:
            database_url: URL Postgres (`DATABASE_URL`).
            connect_timeout: Batas waktu membuka satu koneksi, dalam detik.
        """
        self._database_url = database_url
        self._connect_timeout = connect_timeout
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> AsyncEngine:
        """Buat engine dan cek koneksi.

        Returns:
            Engine yang siap dipakai repository.

        Raises:
            DatabaseAlreadyOpenError: Jika provider ini masih terbuka.
            DatabaseUnavailableError: Jika Postgres tidak bisa dihubungi.
        """
        if self._exit_stack is not None:
            raise DatabaseAlreadyOpenError("Database engine is already open")
        engine = create_database_engine(self._database_url, self._connect_timeout)
        async with AsyncExitStack() as exit_stack:
            exit_stack.push_async_callback(engine.dispose)
            await self._check_connection(engine)
            # pop_all memindahkan dispose ke __aexit__. Jika cek gagal, engine langsung ditutup.
            self._exit_stack = exit_stack.pop_all()
        return engine

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup semua koneksi di pool. Aman dipanggil walau provider belum dibuka."""
        exit_stack = self._exit_stack
        self._exit_stack = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def _check_connection(self, engine: AsyncEngine) -> None:
        """Jalankan query kecil untuk memastikan database terjangkau.

        Raises:
            DatabaseUnavailableError: Jika koneksi gagal.
        """
        try:
            async with engine.connect() as connection:
                await connection.execute(text(CONNECTION_CHECK_SQL))
        except OperationalError as error:
            location = describe_database(self._database_url)
            raise DatabaseUnavailableError(
                f"Cannot connect to Postgres at {location}. {START_DATABASE_HINT}"
            ) from error
