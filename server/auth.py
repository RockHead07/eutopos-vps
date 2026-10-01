"""Identitas pengguna dari Cloudflare Access (spesifikasi web-upload bagian 8).

Cloudflare Access sudah menyaring pengguna di tepi (daftar email + kode sekali pakai). Di sini token
JWT-nya divalidasi lagi supaya salah konfigurasi di dashboard tidak membuka origin, dan supaya
diketahui siapa yang mengunggah atau menerbitkan.

    CF_ACCESS_TEAM_DOMAIN   https://<team>.cloudflareaccess.com (sama dengan klaim iss)
    CF_ACCESS_AUD           Application Audience (AUD) Tag aplikasi Access
    EUTOPOS_DEV_NO_AUTH=1   hanya untuk uji lokal: semua permintaan dianggap dev@local
"""

import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request

HEADER = "Cf-Access-Jwt-Assertion"
DEV_USER = "dev@local"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@lru_cache
def _jwks(team: str) -> jwt.PyJWKClient:
    # Kunci dirotasi Cloudflare tiap 6 minggu, PyJWKClient mengambil ulang kalau kid tidak dikenal.
    return jwt.PyJWKClient(f"{team}/cdn-cgi/access/certs", cache_keys=True)


def signing_key(token: str, team: str):
    return _jwks(team).get_signing_key_from_jwt(token).key


def email_from_token(token: str | None) -> str:
    if os.environ.get("EUTOPOS_DEV_NO_AUTH") == "1":
        return DEV_USER
    team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").rstrip("/")
    aud = os.environ.get("CF_ACCESS_AUD", "")
    if not (team and aud):
        # Gagal tertutup: tanpa konfigurasi, rute terlindungi tidak terbuka.
        raise AuthError(
            503, "autentikasi belum dikonfigurasi (CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD)"
        )
    if not token:
        raise AuthError(401, "tidak ada token Cloudflare Access")
    try:
        claims = jwt.decode(
            token, signing_key(token, team), algorithms=["RS256"], audience=aud, issuer=team
        )
    except jwt.PyJWTError as e:
        raise AuthError(403, f"token Cloudflare Access tidak sah: {e}") from e
    if not claims.get("email"):
        raise AuthError(403, "token tanpa email, service token tidak diizinkan")
    return claims["email"]


def current_user(request: Request) -> str:
    try:
        return email_from_token(request.headers.get(HEADER))
    except AuthError as e:
        raise HTTPException(e.status, e.message) from e
