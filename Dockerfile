# The image the compose file builds: the backend only. The frontend is a
# static build served by its own origin (Vite/ nginx); the API holds no
# UI (plan H2/H5).
FROM python:3.12-slim

# The unprivileged user the container runs as (plan G8): the data volumes
# are the only writable paths it needs.
RUN useradd --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt psutil

COPY backend backend
COPY data data

# torch stays out of the base image on purpose: a CPU deployment installs
# the wheel from the CPU index, a GPU one from the CUDA one - the requirements
# file is the same, the index is the choice.
USER app

EXPOSE 8010
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
