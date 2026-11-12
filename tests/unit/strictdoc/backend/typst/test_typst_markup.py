from strictdoc.backend.typst.typst_markup import escape_markup, string_literal


def test_001_escape_markup_escapes_every_markup_character():
    assert (
        escape_markup("# * _ ` $ < > @ [ ] ~ / = - + \\")
        == "\\# \\* \\_ \\` \\$ \\< \\> \\@ \\[ \\] \\~ \\/ \\= \\- \\+ \\\\"
    )


def test_002_escape_markup_escapes_numbered_list_marker_at_line_start():
    assert escape_markup("1. First") == "1\\. First"
    assert escape_markup("a\n 12. b") == "a\n 12\\. b"
    assert escape_markup("version 1.2") == "version 1.2"


def test_003_string_literal_escapes_quotes_backslashes_and_newlines():
    assert string_literal('a "b" \\c\nd\te') == '"a \\"b\\" \\\\c\\nd\\te"'
