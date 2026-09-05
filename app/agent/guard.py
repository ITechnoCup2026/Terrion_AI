"""Penjaga numerik: narasi tidak boleh memuat angka yang tidak dihitung."""

import re

NUMBER = re.compile(r"\d[\d.,]*")


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
