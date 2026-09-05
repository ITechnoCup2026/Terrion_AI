"""Log terstruktur JSON dengan request_id yang merambat dari sisi Go."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Siapkan structlog agar setiap baris keluar sebagai satu objek JSON."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), 20))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), 20)
        ),
        cache_logger_on_first_use=True,
    )


def bind_request(request_id: str) -> None:
    """Ikat request_id ke setiap baris log berikutnya dalam permintaan ini."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)


logger = structlog.get_logger("terrion-ai")
