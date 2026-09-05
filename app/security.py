"""Autentikasi server-ke-server: satu bearer token, tanpa konsep pengguna."""

import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_token(authorization: str = Header(default="")) -> None:
    """Tolak setiap permintaan yang tidak membawa token yang persis cocok.

    compare_digest, bukan ==, supaya waktu eksekusi tidak membocorkan berapa
    banyak byte awal token yang sudah benar. Token kosong menolak semuanya.
    """
    expected = f"Bearer {settings.ai_service_token}"
    if not settings.ai_service_token or not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": ""}},
        )
