"""Galat solver yang boleh ditangkap sebagai jalur degradasi, bukan sebagai bug."""


class SolverFailed(Exception):
    """Solver berjalan tetapi tidak menemukan solusi layak dalam anggarannya."""
