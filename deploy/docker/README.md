# StrictDoc image with Typst and PlantUML

One image for the command line, CI and the web server. It contains:

- StrictDoc, installed from this repository's source.
- Typst 0.15.1, for the `typst-pdf` export and the web UI's
  `Export to PDF (Typst)`.
- PlantUML 1.2026.10 with Java 21 and Graphviz, so that PDFs show PlantUML
  diagrams as drawings. Diagrams are drawn inside the container, with no
  network access. In HTML, PlantUML still runs in the browser as before.
- Optionally Google Chrome, for the `html2pdf` export (`INSTALL_CHROME=true`,
  amd64 only).

## Build

From the repository root:

    docker build -f deploy/docker/Dockerfile -t strictdoc:local .

| Build argument     | Default      | Purpose                                     |
|--------------------|--------------|---------------------------------------------|
| `INSTALL_CHROME`   | `false`      | Adds Chrome for `html2pdf`.                 |
| `PLANTUML_VERSION` | `1.2026.10`  | Change together with `PLANTUML_SHA256`.     |
| `PLANTUML_SHA256`  | (pinned)     | Checksum of the PlantUML jar.               |
| `STRICTDOC_UID`    | `1000`       | UID of the image's `strictdoc` user.        |
| `STRICTDOC_GID`    | `1000`       | GID of the image's `strictdoc` user.        |

The Typst version is the digest-pinned `FROM ghcr.io/typst/typst` line.

## Run

The entrypoint is `strictdoc`. Mount the project at `/data`, and run as your
own user so that the output belongs to you:

    docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" strictdoc:local \
        export . --formats html,typst-pdf

PowerShell:

    docker run --rm -u "$(id -u):$(id -g)" -v "${PWD}:/data" strictdoc:local `
        export . --formats html,typst-pdf

The web server:

    docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" -p 5111:5111 \
        strictdoc:local server /data --host 0.0.0.0

For a shared server with single sign-on, see `deploy/server`, which builds
this image.

Other tools in the image: `typst`, `plantuml`, `git`,
`strictdoc-typst-build` and `strictdoc-new-project`.

## A new project

`strictdoc-new-project` sets up a new project in the SysML tracker layout:
a `strictdoc_config.py` with the tracker layout, item versioning and the
Typst PDF export, the model root `model/MODEL.sysml`, the StrictDoc
libraries, a `.gitignore`, and a Git repository. In an empty folder:

    docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" \
        --entrypoint strictdoc-new-project strictdoc:local --title "My project"

Then start the server (see above) and add trackers, folders and items at
`/workspace`. The script writes nothing if one of its files exists.

An image built on this one sets the Typst settings of new projects with
`STRICTDOC_NEW_TYPST_TEMPLATE`, `STRICTDOC_NEW_TYPST_DEFAULT_DOC_NO`,
`STRICTDOC_NEW_TYPST_DEFAULT_VERSION` and
`STRICTDOC_NEW_TYPST_BUILDER_IMAGE` (the image that builds the PDFs outside
this one). By default a new project uses StrictDoc's own template.

## PDFs with diagrams

Without further configuration, `typst-pdf` compiles with `typst compile`,
and diagrams appear as their source text. To draw the PlantUML diagrams,
let the image's `strictdoc-typst-build` do the build. In
`strictdoc_config.py`:

```python
import shutil

from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    # Only the image has strictdoc-typst-build. Elsewhere, the export
    # falls back to typst compile, with diagrams as source text.
    in_image = shutil.which("strictdoc-typst-build") is not None
    return ProjectConfig(
        project_features=["TYPST_PDF"],
        typst_kroki=in_image,
        typst_pdf_command=(
            ["strictdoc-typst-build", "{dir}"] if in_image else None
        ),
    )
```

`strictdoc-typst-build <folder>`:

1. Copies the files of `/opt/strictdoc-typst/templates` (`kroki.typ`, and
   the report template of an image built on this one) into the folder.
2. Draws each PlantUML block to `.kroki-cache/<name>.svg`, in one Java run.
   A diagram with an error shows PlantUML's error image in the PDF.
3. Compiles each document to a PDF.

Only PlantUML is drawn. Mermaid and other diagrams stay source text.

| Environment variable        | Default                          |
|-----------------------------|----------------------------------|
| `STRICTDOC_TYPST_TEMPLATES` | `/opt/strictdoc-typst/templates` |
| `STRICTDOC_TYPST_PDF_NAME`  | `{file}.pdf`. Fields: `{file}`, `{doc_no}`, `{version}`, `{title}`. |
| `PLANTUML_JAR`              | `/opt/plantuml/plantuml.jar`     |

## A company report template

An external `typst_template` is not part of this repository. Put it in a
small image built on this one, in the repository that owns the template:

```dockerfile
ARG BASE_IMAGE=strictdoc:local
FROM ${BASE_IMAGE}

# <name>.typ with the function <name>, and the files it uses.
COPY company-report.typ /opt/strictdoc-typst/templates/
COPY assets/ /opt/strictdoc-typst/templates/assets/
# Fonts: Typst reads TYPST_FONT_PATHS.
COPY fonts/ /usr/local/share/fonts/
ENV TYPST_FONT_PATHS=/usr/local/share/fonts \
    STRICTDOC_TYPST_PDF_NAME="{doc_no}_{version}-{title}.pdf"
```

The project then sets `typst_template="company-report"` together with the
two options above.

## Publish

For example to the GitHub Container Registry:

    docker build -f deploy/docker/Dockerfile -t ghcr.io/<owner>/strictdoc:<version> .
    docker push ghcr.io/<owner>/strictdoc:<version>

The image is amd64 only: the pinned Typst image has no arm64 build.
