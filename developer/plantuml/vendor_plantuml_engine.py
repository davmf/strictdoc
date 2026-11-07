"""
Vendors the PlantUML TeaVM engine of a PlantUML checkout into StrictDoc.

TeaVM compiles PlantUML to an ES2015 module (plantuml.js) that ends with a
single `export{...}` statement and has no import. ES module scripts are
CORS-blocked when a page is opened via file://, so this script turns the
module into a classic script that defines window.PlantUMLCore, by wrapping
the module body into a function and returning the exports from it.

Usage, from the root of the StrictDoc repository:

    (cd <plantuml> && ./gradlew teavm -Pfast --offline)
    python developer/plantuml/vendor_plantuml_engine.py <plantuml>

The script writes plantuml-core.js, viz-global.js, elk.bundled.js,
LICENSE-PLANTUML and README.txt into
strictdoc/features/plantuml/assets/plantuml/. The README records the
PlantUML version and commit that the engine was built from.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

ASSETS_DIR = os.path.join(
    "strictdoc", "features", "plantuml", "assets", "plantuml"
)

EXPORT_PATTERN = re.compile(r"export\s*\{([^}]*)\}\s*;?\s*$")

HEADER = """\
/*
 * PlantUML {version} ({commit}), compiled to JavaScript with TeaVM, from
 * {repository} ({branch}).
 *
 * Converted from the ES2015 module that TeaVM writes into a classic script
 * by developer/plantuml/vendor_plantuml_engine.py, so that pages opened
 * via file:// can load it. Exposes window.PlantUMLCore with the exports
 * of the module: {exports}.
 *
 * PlantUML is free software, distributed under the GNU General Public
 * License v3.0 or later. See LICENSE-PLANTUML and README.txt.
 */
"""

README = """\
PlantUML engine for StrictDoc
=============================

plantuml-core.js is PlantUML compiled to JavaScript with TeaVM, converted
into a classic script that defines window.PlantUMLCore. viz-global.js is
Viz.js (Graphviz compiled to WebAssembly), which the engine uses for the
layout of most diagram types. elk.bundled.js is elkjs, the Eclipse Layout
Kernel, which the engine loads on demand for `!pragma layout elk`. The SysML
requirements view uses it by default.

Source:   {repository}
Branch:   {branch}
Commit:   {commit}
Version:  {version}
Exports:  {exports}

To update, build the engine in the PlantUML checkout and vendor it:

    (cd <plantuml> && ./gradlew teavm -Pfast --offline)
    python developer/plantuml/vendor_plantuml_engine.py <plantuml>

Not vendored: the standard library bundles (`!include <C4/...>` and so on), emoji.js,
openiconic.js and themes.js. The engine loads them on demand, next to
plantuml-core.js, and reports an error when they are missing.

License: PlantUML is distributed under the GNU General Public License v3.0
or later (LICENSE-PLANTUML). Viz.js is MIT licensed and contains Graphviz
(Eclipse Public License 1.0) and Expat (MIT), see the header of
viz-global.js. elkjs is distributed under the Eclipse Public License 2.0, see
the header of elk.bundled.js.
"""


def git_output(checkout: str, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", checkout, *arguments], text=True
    ).strip()


def repository_url(checkout: str) -> str:
    url = git_output(checkout, "remote", "get-url", "origin")
    match = re.match(r"git@([^:]+):(.+?)(\.git)?$", url)
    if match is not None:
        return f"https://{match.group(1)}/{match.group(2)}"
    return url


def read_version(checkout: str) -> str:
    with open(
        os.path.join(checkout, "gradle.properties"), encoding="utf-8"
    ) as file_:
        for line_ in file_:
            key, _, value = line_.partition("=")
            if key.strip() == "version":
                return value.strip()
    return "unknown"


def convert_module(module_text: str) -> tuple:
    """
    Return the classic script body and the names of the exports.
    """
    match = EXPORT_PATTERN.search(module_text)
    if match is None:
        raise ValueError("plantuml.js does not end with an export statement")
    body = module_text[: match.start()]
    if re.search(r"(^|[;}\s])(import|export)\s*[{*]", body) is not None:
        raise ValueError("plantuml.js has more than one import or export")
    entries = []
    names = []
    for item_ in match.group(1).split(","):
        local_name, _, exported_name = item_.strip().partition(" as ")
        exported_name = exported_name.strip() or local_name.strip()
        entries.append(f"{exported_name}: {local_name.strip()}")
        names.append(exported_name)
    if body.startswith('"use strict";'):
        body = body[len('"use strict";') :]
    script = (
        "var PlantUMLCore = (function () {\n"
        '"use strict";\n'
        + body
        + "\nreturn { "
        + ", ".join(entries)
        + " };\n})();\n"
    )
    return script, names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("plantuml_checkout")
    args = parser.parse_args()
    checkout = os.path.abspath(args.plantuml_checkout)
    teavm_dir = os.path.join(checkout, "build", "generated", "teavm", "js")

    with open(
        os.path.join(teavm_dir, "plantuml.js"), encoding="utf-8"
    ) as file_:
        script, names = convert_module(file_.read())

    details = {
        "repository": repository_url(checkout),
        "branch": git_output(checkout, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": git_output(checkout, "rev-parse", "HEAD"),
        "version": read_version(checkout),
        "exports": ", ".join(names),
    }
    with open(
        os.path.join(ASSETS_DIR, "plantuml-core.js"), "w", encoding="utf-8"
    ) as file_:
        file_.write(HEADER.format(**details))
        file_.write(script)
    for script_ in ("viz-global.js", "elk.bundled.js"):
        shutil.copyfile(
            os.path.join(teavm_dir, script_),
            os.path.join(ASSETS_DIR, script_),
        )
    shutil.copyfile(
        os.path.join(checkout, "LICENSE"),
        os.path.join(ASSETS_DIR, "LICENSE-PLANTUML"),
    )
    with open(
        os.path.join(ASSETS_DIR, "README.txt"), "w", encoding="utf-8"
    ) as file_:
        file_.write(README.format(**details))
    print(  # noqa: T201
        f"Vendored PlantUML {details['version']} ({details['commit']})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
