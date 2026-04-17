ARG ARCH=

FROM ${ARCH}python:alpine

LABEL maintainer="routmoute"
LABEL description="Lightweight NTP proxy with timezone and DST support"
LABEL version="1.0"

RUN apk update --no-cache && \
    pip install ntplib && \
    apk add --no-cache netcat-openbsd && \
    adduser -D -u 1000 ntpproxy

ENV TZ="Europe/Paris"
ENV NTP_SERVERS="0.pool.ntp.org,1.pool.ntp.org"

WORKDIR /app
COPY ./app/server.py .

USER ntpproxy

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD timeout 2 sh -c 'echo -n "" | nc -u 127.0.0.1 123 > /dev/null' || exit 1

CMD ["python", "server.py"]
