# syntax=docker/dockerfile:1.7
#
# StrictDoc with Typst and PlantUML, built from this repository's source.
# One image for the command line and for the web server. See README.md.
#
# Build from the repository root:
#   docker build -f deploy/docker/Dockerfile -t strictdoc:local .
#
# Export a project in the current folder:
#   docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" strictdoc:local \
#       export . --formats html,typst-pdf
#
# The PDF build draws PlantUML diagrams offline, with no network access.

# Pinned by digest. Refresh the tag and digest together.
FROM ghcr.io/typst/typst:0.15.1@sha256:032e292249bcd378480cc7c142cfa324b63ef8aadeb88d7e7230320c4c9c422f AS typst

FROM python:3.12-slim-trixie

ARG PLANTUML_VERSION=1.2026.10
ARG PLANTUML_SHA256=e9bc9e6b2eb715e8c0c929f3dcb5fc1923be13f37599b09c293c66d354e88686
# Chrome is only needed for the HTML-to-PDF export (html2pdf), and only
# exists for amd64.
ARG INSTALL_CHROME=false
ARG STRICTDOC_UID=1000
ARG STRICTDOC_GID=1000

# Java and Graphviz draw PlantUML diagrams. The DejaVu fonts give PlantUML
# its text metrics and Typst the fonts of the SVG files.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fontconfig \
    fonts-dejavu-core \
    git \
    graphviz \
    openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "$INSTALL_CHROME" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends curl \
      && curl -fsSL -o /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
      && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
      && rm /tmp/google-chrome.deb \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY --from=typst /bin/typst /usr/local/bin/typst

ADD --checksum=sha256:${PLANTUML_SHA256} \
    https://github.com/plantuml/plantuml/releases/download/v${PLANTUML_VERSION}/plantuml-${PLANTUML_VERSION}.jar \
    /opt/plantuml/plantuml.jar
RUN chmod 644 /opt/plantuml/plantuml.jar \
    && printf '#!/bin/sh\nexec java -Djava.awt.headless=true -jar /opt/plantuml/plantuml.jar "$@"\n' \
       > /usr/local/bin/plantuml \
    && chmod 755 /usr/local/bin/plantuml

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md LICENSE NOTICE /src/
COPY strictdoc /src/strictdoc
RUN pip install --no-cache-dir /src && rm -rf /src

# The PDF build of typst_pdf_command. An image built on this one adds its
# report template and assets to /opt/strictdoc-typst/templates.
COPY --chmod=755 deploy/docker/strictdoc-typst-build /usr/local/bin/strictdoc-typst-build
# Sets up a new project in the tracker layout. See README.md.
COPY --chmod=755 deploy/docker/strictdoc-new-project /usr/local/bin/strictdoc-new-project
# The PowerShell script that runs the image, which strictdoc-launcher prints
# with the image's name. An image built on this one sets
# STRICTDOC_IMAGE_NAME to its own name.
COPY deploy/docker/strictdoc.ps1 /usr/local/share/strictdoc/strictdoc.ps1
COPY --chmod=755 deploy/docker/strictdoc-launcher /usr/local/bin/strictdoc-launcher
COPY deploy/docker/kroki.typ /opt/strictdoc-typst/templates/kroki.typ

# The project folder usually belongs to a host user, so Git would refuse to
# work in it without this.
RUN git config --system safe.directory '*'

RUN groupadd -g "$STRICTDOC_GID" strictdoc \
    && useradd -m -u "$STRICTDOC_UID" -g "$STRICTDOC_GID" -s /bin/bash strictdoc \
    && mkdir -p /data /var/lib/strictdoc \
    && chown strictdoc:strictdoc /data /var/lib/strictdoc

# "docker run -u <uid>:<gid>" runs as a user without a home folder, so keep
# the caches somewhere every user can write.
ENV XDG_CACHE_HOME=/tmp/.cache \
    PLANTUML_JAR=/opt/plantuml/plantuml.jar \
    STRICTDOC_TYPST_TEMPLATES=/opt/strictdoc-typst/templates \
    STRICTDOC_IMAGE_NAME=strictdoc:local

USER strictdoc
WORKDIR /data
EXPOSE 5111

ENTRYPOINT ["strictdoc"]
CMD ["--help"]
