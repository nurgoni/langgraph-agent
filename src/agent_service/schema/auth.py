"""Model request dan response login (FR-33), dipakai bersama service, client, dan UI.

>>> LoginRequest(username="  Demo.User ", password="secret").username
'demo.user'
>>> TokenResponse(access_token="t", expires_in=60, user_id="u1", username="demo").token_type
'bearer'
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints

# Huruf kecil, angka, titik, minus, dan underscore. Diawali huruf atau angka, 3–32 karakter.
USERNAME_PATTERN: Final = r"^[a-z0-9][a-z0-9._-]{2,31}$"
PASSWORD_MIN_LENGTH: Final = 8
# Batas atas mencegah request dengan password raksasa membebani hash argon2.
PASSWORD_MAX_LENGTH: Final = 128

type TokenRole = Literal["user", "service"]


def normalize_username(value: object) -> object:
    """Buang spasi di tepi dan ubah ke huruf kecil, sebelum pola username dicek.

    >>> normalize_username("  Demo ")
    'demo'
    """
    return value.strip().lower() if isinstance(value, str) else value


# BeforeValidator: `pattern` di StringConstraints dicek sebelum `to_lower`, jadi normalisasi harus
# terjadi lebih dulu.
Username = Annotated[
    str, BeforeValidator(normalize_username), StringConstraints(pattern=USERNAME_PATTERN)
]


class LoginRequest(BaseModel):
    """Body `POST /auth/login`."""

    username: Username = Field(examples=["demo"])
    # Panjang minimum hanya diperiksa saat akun dibuat, supaya login tidak membocorkan aturannya.
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class TokenResponse(BaseModel):
    """Access token JWT. Kirim sebagai `Authorization: Bearer <access_token>`."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Umur token dalam detik.", examples=[43200])
    user_id: str
    username: str
    role: TokenRole = "user"
