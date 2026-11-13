import os
import re
import shutil
import sys
from typing import List, Optional

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))
PATH_TO_OUTPUT_FOLDER = os.path.join(PATH_TO_THIS_TEST_FOLDER, "output")
PATH_TO_FAKE_BUILDER = os.path.join(PATH_TO_THIS_TEST_FOLDER, "fake_builder.py")


def create_client(
    typst_pdf_command: Optional[List[str]],
    typst_template: str = "company-report",
) -> TestClient:
    shutil.rmtree(PATH_TO_OUTPUT_FOLDER, ignore_errors=True)
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=PATH_TO_THIS_TEST_FOLDER,
        output_path=PATH_TO_OUTPUT_FOLDER,
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    project_config: ProjectConfig = ProjectConfig.default_config()
    project_config.project_features.append(ProjectFeature.TYPST_PDF)
    project_config.typst_pdf_command = typst_pdf_command
    project_config.typst_template = typst_template
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


def get_document_mid(client: TestClient) -> str:
    response = client.get("/25_export_document_to_typst_pdf/sample.html")
    assert response.status_code == 200
    match_document_mid = re.search(
        r"/export_typst_pdf/(?P<document_mid>[a-z0-9]+)",
        response.content.decode(),
    )
    assert match_document_mid is not None
    return match_document_mid.group("document_mid")


def test_01_export_document_to_typst_pdf():
    client = create_client([sys.executable, PATH_TO_FAKE_BUILDER, "{dir}"])
    document_mid = get_document_mid(client)

    response = client.get(f"/export_typst_pdf/{document_mid}")
    assert response.status_code == 200, response.content
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''298_1013_02-Sample-document.pdf"
    )
    exported_typ = response.content.decode()
    assert "#show: company-report.with(" in exported_typ
    assert '  doc_no: "298_1013",' in exported_typ
    assert '(uid: "REQ-1", title: [Requirement 1]' in exported_typ


def test_02_failed_build_returns_the_builder_output():
    client = create_client(
        [sys.executable, "-c", "import sys; print('no Kroki'); sys.exit(3)"]
    )
    document_mid = get_document_mid(client)

    response = client.get(f"/export_typst_pdf/{document_mid}")
    assert response.status_code == 500
    assert response.content.decode() == (
        "Typst PDF: the build failed with exit code 3:\n\nno Kroki\n"
    )


def test_03_unknown_document_returns_404():
    client = create_client([sys.executable, PATH_TO_FAKE_BUILDER, "{dir}"])

    response = client.get("/export_typst_pdf/0123456789abcdef")
    assert response.status_code == 404


def test_04_missing_image_error_explains_how_to_build_it():
    client = create_client(
        [
            sys.executable,
            "-c",
            (
                "import sys; print(\"Unable to find image 'x' locally\"); "
                "sys.exit(125)"
            ),
        ]
    )
    document_mid = get_document_mid(client)

    response = client.get(f"/export_typst_pdf/{document_mid}")
    assert response.status_code == 500
    assert "Build it locally" in response.content.decode()
    assert "typst_pdf_builder_image" in response.content.decode()


def test_05_generic_template_by_default():
    client = create_client(
        [sys.executable, PATH_TO_FAKE_BUILDER, "{dir}"],
        typst_template=ProjectConfig.default_config().typst_template,
    )
    document_mid = get_document_mid(client)

    response = client.get(f"/export_typst_pdf/{document_mid}")
    assert response.status_code == 200, response.content
    exported_typ = response.content.decode()
    assert '#import "strictdoc-report.typ": strictdoc-report' in exported_typ
    assert "#show: strictdoc-report.with(" in exported_typ
    assert "company-report" not in exported_typ


def test_06_external_template_without_builder_image_explains_the_option():
    client = create_client(None)
    document_mid = get_document_mid(client)

    response = client.get(f"/export_typst_pdf/{document_mid}")
    assert response.status_code == 500
    assert "typst_pdf_builder_image" in response.content.decode()
