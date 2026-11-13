"""
A stand-in for the build image of an external template. It writes one PDF file per
report .typ file of the folder, and fails when the folder has no
strictdoc.typ. The PDF file contains the .typ file, so that the test can
check what the server exported.
"""

import glob
import os
import sys

path_to_dir = sys.argv[1]
if not os.path.isfile(os.path.join(path_to_dir, "strictdoc.typ")):
    print("strictdoc.typ is missing")  # noqa: T201
    sys.exit(1)
for path_to_typ_ in glob.glob(os.path.join(path_to_dir, "*.typ")):
    if os.path.basename(path_to_typ_) in (
        "strictdoc.typ",
        "strictdoc-report.typ",
    ):
        continue
    with open(path_to_typ_, encoding="utf8") as typ_file_:
        content = typ_file_.read()
    with open(
        os.path.join(path_to_dir, "298_1013_02-Sample-document.pdf"),
        "w",
        encoding="utf8",
    ) as pdf_file_:
        pdf_file_.write(content)
print("built")  # noqa: T201
