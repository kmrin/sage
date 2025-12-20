FROM ubuntu:24.04

ENV PYTHONPATH /sage
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

RUN apt update && \
    apt install -y python3 python3-dev python3-pip python3-venv libmagic-dev ffmpeg libffi-dev libnacl-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /sage

RUN mkdir -p \
    /var/sage/data/temp \
    /var/sage/logs/history \
    /var/sage/logs/tracebacks

COPY ./pyproject.toml .
COPY ./entrypoint.sh .
COPY ./alembic.ini ./
COPY ./migrations ./migrations
COPY ./sage ./sage

RUN chmod -R 777 /var/sage
RUN chmod +x entrypoint.sh

RUN python3 -m venv /sage/venv
RUN /sage/venv/bin/pip install --no-cache-dir -e .

CMD ["./entrypoint.sh"]