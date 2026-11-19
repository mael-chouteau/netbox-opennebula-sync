FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends snmp \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin sync

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && chown -R sync:sync /app

USER sync
ENTRYPOINT ["netbox-opennebula-sync"]
CMD ["daemon"]
