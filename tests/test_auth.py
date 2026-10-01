"""Uji validasi JWT Cloudflare Access dengan kunci RSA uji, tanpa jaringan."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server import auth

TEAM = "https://tim-uji.cloudflareaccess.com"
AUD = "aud-uji"


@pytest.fixture
def key(monkeypatch):
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    monkeypatch.setattr(auth, "signing_key", lambda token, team: k.public_key())
    return k


def token(key, **claims):
    body = {"aud": AUD, "iss": TEAM, "email": "a@x.id", "exp": time.time() + 600, **claims}
    return jwt.encode(body, key, algorithm="RS256")


def test_valid_token_gives_email(key):
    assert auth.email_from_token(token(key)) == "a@x.id"


@pytest.mark.parametrize(
    "claims,status",
    [
        ({"aud": "aplikasi-lain"}, 403),
        ({"iss": "https://tim-lain.cloudflareaccess.com"}, 403),
        ({"exp": time.time() - 10}, 403),
        ({"email": None}, 403),
    ],
    ids=["aud-salah", "iss-salah", "kedaluwarsa", "tanpa-email"],
)
def test_bad_tokens_are_rejected(key, claims, status):
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token(token(key, **claims))
    assert e.value.status == status


def test_missing_token_is_401(key):
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token(None)
    assert e.value.status == 401


def test_unconfigured_is_503_not_open(monkeypatch):
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token("apa saja")
    assert e.value.status == 503


def test_dev_mode(monkeypatch):
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    assert auth.email_from_token(None) == auth.DEV_USER


def test_dev_mode_never_overrides_real_config(key, monkeypatch):
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")  # konfigurasi Access ada (fixture key)
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token(None)
    assert e.value.status == 401
