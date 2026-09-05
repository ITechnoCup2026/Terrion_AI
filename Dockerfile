FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8080

# Satu worker, dan itu bukan penghematan memori: dua proses berarti dua state
# RNG yang berbeda, dan itu melanggar jaminan determinisme kontrak.
#
# Port dibaca dari $PORT kalau ada. Railway menyuntikkan variabel itu dan
# memakai nilainya juga untuk health check, jadi mengeraskan 8080 di sana
# berarti health check menunggu port yang salah lalu gagal setelah timeout.
# Fly.io tidak menyuntikkannya; cadangan 8080 cocok dengan internal_port di
# fly.toml. Bentuk shell dipakai justru supaya ${PORT} sempat diperluas, dan
# exec supaya uvicorn tetap PID 1 dan menerima SIGTERM saat redeploy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
