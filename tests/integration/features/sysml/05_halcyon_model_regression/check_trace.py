"""
Check that every SYS requirement page block shows the design trace.

Usage: check_trace.py <system_requirements.sysml> <system_requirements.html>

Each SYS requirement is listed in the SysML source. In the exported HTML,
the requirement's block runs from its data-uid attribute to the next
data-uid attribute. The block must show "Satisfied by" and "Verified by".
"""

import re
import sys


def main() -> int:
    path_to_sysml, path_to_html = sys.argv[1], sys.argv[2]
    with open(path_to_sysml, encoding="utf8") as file_:
        sysml_text = file_.read()
    with open(path_to_html, encoding="utf8") as file_:
        html_text = file_.read()

    uids = re.findall(r"requirement <'(SYS-[A-Z0-9-]+)'", sysml_text)
    if len(uids) == 0:
        print("error: no SYS requirements found")  # noqa: T201
        return 1

    block_starts = [
        (match_.start(), match_.group(1))
        for match_ in re.finditer(r'data-uid="([^"]*)"', html_text)
    ]
    failed = 0
    for uid_ in uids:
        start = None
        end = len(html_text)
        for index_, (position_, uid_value_) in enumerate(block_starts):
            if uid_value_ == uid_:
                start = position_
                end = (
                    block_starts[index_ + 1][0]
                    if index_ + 1 < len(block_starts)
                    else len(html_text)
                )
                break
        if start is None:
            print(f"error: no HTML block for {uid_}")  # noqa: T201
            failed += 1
            continue
        block = html_text[start:end]
        for label_ in ("Satisfied by", "Verified by"):
            if label_ not in block:
                print(f"error: {uid_} has no '{label_}' relation")  # noqa: T201
                failed += 1
    print(f"Checked {len(uids)} SYS requirements, failures: {failed}")  # noqa: T201
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
