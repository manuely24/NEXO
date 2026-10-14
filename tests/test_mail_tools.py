import json

import pytest

from nexo.core.models import DataClass
from nexo.tools.mail_tools import MailGetPendingTool


def test_mail_pending_is_classified_confidential_and_filters_done(tmp_path):
    (tmp_path / "mail.json").write_text(
        json.dumps(
            [
                {"subject": "Entrega", "status": "pending"},
                {"subject": "Antiguo", "status": "done"},
            ]
        ),
        encoding="utf-8",
    )
    tool = MailGetPendingTool(tmp_path)

    result = json.loads(tool.run({"path": "mail.json"}))

    assert tool.data_class == DataClass.CONFIDENTIAL
    assert len(result) == 1
    assert result[0]["classification"] == "confidential"


def test_mail_tool_rejects_paths_outside_workspace(tmp_path):
    tool = MailGetPendingTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run({"path": "../mail.json"})


def test_mail_sanitizer_marks_local_data_and_omits_content(tmp_path):
    (tmp_path / "sensitive.json").write_text(
        json.dumps([{"subject": "Password reset", "body": "token=secret-value"}]),
        encoding="utf-8",
    )

    result = json.loads(MailGetPendingTool(tmp_path).run({"path": "sensitive.json"}))

    assert result[0]["classification"] == "local"
    assert result[0]["body"] == "[LOCAL DATA OMITTED]"
    assert "secret-value" not in json.dumps(result)


def test_eml_parser_extracts_body_without_including_attachment(tmp_path):
    eml = tmp_path / "notice.eml"
    eml.write_text(
        "From: campus@example.test\n"
        "Subject: SQL delivery\n"
        "MIME-Version: 1.0\n"
        "Content-Type: multipart/mixed; boundary=boundary\n\n"
        "--boundary\nContent-Type: text/plain; charset=utf-8\n\n"
        "Entrega el viernes.\n"
        "--boundary\nContent-Type: application/octet-stream\n"
        "Content-Disposition: attachment; filename=secret.bin\n\n"
        "ATTACHMENT_SECRET\n--boundary--\n",
        encoding="utf-8",
    )

    result = json.loads(MailGetPendingTool(tmp_path).run({"path": "notice.eml"}))

    assert result[0]["classification"] == "confidential"
    assert "Entrega el viernes" in result[0]["body"]
    assert "ATTACHMENT_SECRET" not in json.dumps(result)