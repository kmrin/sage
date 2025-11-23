FROM ubuntu:24.04

ENV PATH="/sage/bin:${PATH}"
ENV PYTHONPATH /sage
ENV PYTHONDONTWRITEBYTECODE 1

RUN apt update && \
    apt install -y python3 python3-dev python3-pip python3-venv libmagic-dev ffmpeg libffi-dev libnacl-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /sage

RUN mkdir -p \
    /var/sage/data/temp \
    /var/sage/logs/history \
    /var/sage/logs/tracebacks

COPY ./requirements.txt .
COPY ./entrypoint.sh .
# COPY ./bin .

RUN chmod -R 777 /var/sage
RUN chmod +x entrypoint.sh
# RUN chmod -R +x bin

RUN python3 -m venv /sage/venv
RUN /sage/venv/bin/pip install --no-cache-dir -r requirements.txt

# EXPOSE 8000

CMD ["./entrypoint.sh"]