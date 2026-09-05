"""Penjaga narasi: teksnya harus ada isinya, dan angkanya harus terhitung."""

import re

NUMBER = re.compile(r"\d[\d.,]*")

# Narasi templat terpendek yang pernah dihasilkan panjangnya di atas 300
# karakter. 60 adalah lantai yang longgar: cukup rendah untuk tidak pernah
# menolak paragraf yang sungguh ditulis, cukup tinggi untuk menangkap
# jawaban model yang habis sebelum mulai.
MIN_CHARS = 60


def ungrounded_numbers(text: str, allowed: frozenset[str]) -> list[str]:
    """Setiap token angka di teks yang tidak ada di daftar angka terhitung."""
    found = []
    for match in NUMBER.finditer(text):
        token = match.group().rstrip(".,")
        if token and token not in allowed:
            found.append(token)
    return found


def numbers_are_grounded(text: str, allowed: frozenset[str]) -> bool:
    """Benar bila setiap angka di teks berasal dari blok fakta."""
    return not ungrounded_numbers(text, allowed)


def rejection_reason(text: str, allowed: frozenset[str], truncated: bool = False) -> str | None:
    """Alasan menolak narasi model, atau None kalau teksnya layak dipakai.

    Urutan pemeriksaan disengaja. Teks kosong tidak memuat satu pun angka,
    jadi ia LOLOS pemeriksaan angka — itulah cara jawaban kosong bisa
    menggantikan narasi templat yang sudah benar dan diberi label "llm".
    Karena itu bentuk teksnya diperiksa lebih dulu, baru isinya.
    """
    if truncated:
        return "truncated"
    if len(text.strip()) < MIN_CHARS:
        return "narrative_too_short"
    if ungrounded_numbers(text, allowed):
        return "ungrounded_numbers"
    return None
