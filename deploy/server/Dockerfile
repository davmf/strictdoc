# StrictDoc web server image, built from this repository's source.
#
# Build from the repository root:
#   docker build -f deploy/server/Dockerfile -t strictdoc-server .
#
# The project to serve is mounted at /data (a Git clone). Generated HTML and
# caches go to /var/lib/strictdoc, outside the project.

FROM ubuntu:24.04

ARG INSTALL_CHROME=true
ARG STRICTDOC_UID=1000
ARG STRICTDOC_GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    python3 \
    python3-venv \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Chrome is only needed for PDF printing from the web UI.
RUN if [ "$INSTALL_CHROME" = "true" ]; then \
      wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
      && apt-get update \
      && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
      && rm /tmp/google-chrome.deb \
      && rm -rf /var/lib/apt/lists/*; \
    fi

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md LICENSE NOTICE /src/
COPY strictdoc /src/strictdoc
RUN pip install --no-cache-dir /src && rm -rf /src

# The project volume is usually owned by a host user, so Git would refuse to
# work in it without this.
RUN git config --system safe.directory '*'

RUN userdel -r ubuntu 2>/dev/null || true \
    && groupadd -g "$STRICTDOC_GID" strictdoc \
    && useradd -m -u "$STRICTDOC_UID" -g "$STRICTDOC_GID" -s /bin/bash strictdoc \
    && mkdir -p /data /var/lib/strictdoc \
    && chown strictdoc:strictdoc /data /var/lib/strictdoc

USER strictdoc
WORKDIR /data
EXPOSE 5111

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5111/healthz', timeout=4)"

# One process, one worker, no reload: the server keeps the whole project
# model in memory and relies on in-process locks.
ENTRYPOINT ["strictdoc", "server", "/data", \
            "--host", "0.0.0.0", "--port", "5111", \
            "--output-path", "/var/lib/strictdoc/output"]
CMD ["--watch"]
