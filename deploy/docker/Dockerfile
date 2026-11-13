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

# A Java runtime with only the modules PlantUML uses, about a third of the
# size of Debian's JRE. Pinned by digest. Refresh the tag and digest together.
FROM eclipse-temurin:21-jdk@sha256:0a3f329821dcadf54b2a3033a15e2e9f007069a9db43d7f51897e6b80e726b07 AS jre
RUN jlink \
      --add-modules java.base,java.desktop,java.logging,java.prefs,java.scripting,java.xml,jdk.charsets,jdk.unsupported \
      --strip-debug --no-header-files --no-man-pages --compress=zip-6 \
      --output /opt/jre

# StrictDoc in a virtual environment. Built in its own stage, so that the
# sources and the build files stay out of the image.
# The html2pdf extra (html2pdf4doc, Selenium, pypdf) only comes with Chrome.
FROM python:3.12-slim-trixie AS venv
ARG INSTALL_CHROME=false
RUN python3 -m venv /opt/venv
COPY pyproject.toml README.md LICENSE NOTICE /src/
COPY strictdoc /src/strictdoc
RUN if [ "$INSTALL_CHROME" = "true" ]; then extra="[html2pdf]"; else extra=""; fi \
    && /opt/venv/bin/pip install --no-cache-dir "/src${extra}"

FROM python:3.12-slim-trixie

ARG PLANTUML_VERSION=1.2026.10
ARG PLANTUML_SHA256=e9bc9e6b2eb715e8c0c929f3dcb5fc1923be13f37599b09c293c66d354e88686
# Chrome is only needed for the HTML-to-PDF export (html2pdf), and only
# exists for amd64.
ARG INSTALL_CHROME=false
ARG STRICTDOC_UID=1000
ARG STRICTDOC_GID=1000

# Java and Graphviz draw PlantUML diagrams. The DejaVu fonts give PlantUML
# its text metrics and Typst the fonts of the SVG files. Java's AWT needs
# FreeType and fontconfig.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fontconfig \
    fonts-dejavu-core \
    git \
    graphviz \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

COPY --from=jre /opt/jre /opt/java
ENV JAVA_HOME=/opt/java

RUN if [ "$INSTALL_CHROME" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends curl \
      && curl -fsSL -o /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
      && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
      && rm /tmp/google-chrome.deb \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY --from=typst /bin/typst /usr/local/bin/typst

# --chmod also sets the mode of the folder it creates, so it must keep x.
ADD --checksum=sha256:${PLANTUML_SHA256} --chmod=755 \
    https://github.com/plantuml/plantuml/releases/download/v${PLANTUML_VERSION}/plantuml-${PLANTUML_VERSION}.jar \
    /opt/plantuml/plantuml.jar
RUN printf '#!/bin/sh\nexec java -Djava.awt.headless=true -jar /opt/plantuml/plantuml.jar "$@"\n' \
       > /usr/local/bin/plantuml \
    && chmod 755 /usr/local/bin/plantuml

COPY --from=venv /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:/opt/java/bin:$PATH"

# The PDF build of typst_pdf_command. An image built on this one adds its
# report template and assets to /opt/strictdoc-typst/templates.
COPY --chmod=755 deploy/docker/strictdoc-typst-build /usr/local/bin/strictdoc-typst-build
# Sets up a new project in the tracker layout. See README.md.
COPY --chmod=755 deploy/docker/strictdoc-new-project /usr/local/bin/strictdoc-new-project
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
    STRICTDOC_TYPST_TEMPLATES=/opt/strictdoc-typst/templates

USER strictdoc
WORKDIR /data
EXPOSE 5111

ENTRYPOINT ["strictdoc"]
CMD ["--help"]
