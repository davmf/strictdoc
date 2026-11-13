"""
html2pdf4doc (with Selenium and pypdf) is an optional dependency, installed
with the html2pdf extra: pip install "strictdoc[html2pdf]". Only the HTML2PDF
export needs it, so StrictDoc imports it when that export runs.
"""

import importlib
import importlib.util
from types import ModuleType

from strictdoc.helpers.exception import StrictDocException

HTML2PDF4DOC_MISSING_MESSAGE = (
    "The HTML2PDF feature needs the html2pdf4doc package, which is not "
    'installed. Install it with: pip install "strictdoc[html2pdf]".'
)


def is_html2pdf4doc_installed() -> bool:
    return importlib.util.find_spec("html2pdf4doc") is not None


def import_html2pdf4doc(module_name: str = "html2pdf4doc") -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as exception_:
        raise StrictDocException(HTML2PDF4DOC_MISSING_MESSAGE) from exception_
