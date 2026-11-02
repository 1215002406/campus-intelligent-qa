import io

import pytest
import pymupdf
from docx import Document as create_docx
from openpyxl import Workbook

from app.ingestion.parsers import UniversalDocumentParser
from app.repositories import UserRepository


def upload(
    client,
    auth,
    *,
    filename="campus.md",
    content=b"# Campus\nLibrary hours",
    title="Campus Guide",
    category="教务",
    overwrite=None,
):
    data = {"title": title, "category": category}
    if overwrite is not None:
        data["overwrite"] = str(overwrite).lower()
    return client.post(
        "/api/admin/documents",
        headers=auth,
        files={"file": (filename, content, "text/markdown")},
        data=data,
    )


def test_document_routes_enforce_role(client, headers):
    assert client.get("/api/admin/documents").status_code == 401
    assert client.get("/api/admin/documents", headers=headers()).status_code == 403
    assert upload(client, headers()).status_code == 403
    assert client.patch("/api/admin/documents/1", json={"category": "教务"}).status_code == 401
    assert client.patch("/api/admin/documents/1", headers=headers(), json={"category": "教务"}).status_code == 403

    auth = headers("admin")
    assert client.get("/api/admin/documents", headers=auth).status_code == 200
    for method, path in (
        ("GET", "/api/admin/documents/1"),
        ("POST", "/api/admin/documents/1/reindex"),
        ("POST", "/api/admin/documents/1/disable"),
        ("POST", "/api/admin/documents/1/enable"),
        ("DELETE", "/api/admin/documents/1"),
    ):
        assert client.request(method, path, headers=auth).status_code == 404
    assert client.patch("/api/admin/documents/1", headers=auth, json={"category": "教务"}).status_code == 404


def test_markdown_upload_is_parsed_chunked_and_saved(client, headers, settings):
    section = "选课期间应核对课程容量、上课时间和考试安排。" * 45
    content = f"# 选课说明\n{section}\n\n# 退课说明\n{section}".encode()
    auth = headers("admin")
    response = upload(client, auth, filename="../../course-guide.md", content=content, title="选课与退课")
    assert response.status_code == 202
    uploaded = response.json()
    assert uploaded["status"] == "pending"
    assert uploaded["original_name"] == "course-guide.md"

    client.app.state.ingestion.wait_idle()
    detail = client.get(f"/api/admin/documents/{uploaded['id']}", headers=auth)
    assert detail.status_code == 200
    document = detail.json()
    assert document["status"] == "ready"
    assert document["index_version"].startswith("idx-")
    assert document["chunk_count"] >= 3
    assert document["error_message"] is None
    assert len(document["chunks"]) == document["chunk_count"]
    assert len(list(settings.upload_dir.iterdir())) == 1


def test_upload_validation_and_duplicate_detection(client, headers, settings):
    auth = headers("admin")
    assert upload(client, auth, filename="bad.exe").status_code == 415
    assert upload(client, auth, filename="empty.txt", content=b"").status_code == 400
    assert not settings.upload_dir.exists() or not list(settings.upload_dir.iterdir())

    first = upload(client, auth, filename="same.txt", content="校园资料".encode())
    assert first.status_code == 202
    duplicate = upload(client, auth, filename="copy.txt", content="校园资料".encode())
    assert duplicate.status_code == 409
    client.app.state.ingestion.wait_idle()


def test_same_filename_requires_confirmation_and_can_be_overwritten(client, headers, settings):
    auth = headers("admin")
    first = upload(
        client,
        auth,
        filename="campus-rules.md",
        content="# 旧规则\n旧版图书馆开放时间。".encode(),
        title="校园规则（旧）",
    )
    assert first.status_code == 202
    document_id = first.json()["id"]
    client.app.state.ingestion.wait_idle()
    old_file = next(settings.upload_dir.iterdir())

    conflict = upload(
        client,
        auth,
        filename="campus-rules.md",
        content="# 新规则\n新版图书馆开放时间。".encode(),
        title="校园规则（新）",
    )
    assert conflict.status_code == 409
    assert "同名文档" in conflict.json()["detail"]
    assert len(client.get("/api/admin/documents", headers=auth).json()) == 1
    assert old_file.exists()

    overwritten = upload(
        client,
        auth,
        filename="campus-rules.md",
        content="# 新规则\n新版图书馆开放时间。".encode(),
        title="校园规则（新）",
        overwrite=True,
    )
    assert overwritten.status_code == 202
    assert overwritten.json()["id"] == document_id
    client.app.state.ingestion.wait_idle()
    detail = client.get(f"/api/admin/documents/{document_id}", headers=auth).json()
    assert detail["title"] == "校园规则（新）"
    assert detail["status"] == "ready"
    assert "新版图书馆开放时间" in detail["chunks"][0]["content"]
    assert not old_file.exists()
    assert len(list(settings.upload_dir.iterdir())) == 1


def test_invalid_text_encoding_is_reported_as_failed(client, headers):
    auth = headers("admin")
    response = upload(client, auth, filename="broken.txt", content=b"\xff\xfe\x00\x81")
    assert response.status_code == 202
    document_id = response.json()["id"]
    client.app.state.ingestion.wait_idle()
    document = client.get(f"/api/admin/documents/{document_id}", headers=auth).json()
    assert document["status"] == "failed"
    assert "UTF-8" in document["error_message"]
    assert document["chunk_count"] == 0


def test_structured_txt_headings_create_separate_chunks(client, headers):
    content = (
        "校园服务说明\n测试文档\n\n"
        "HQ-01 校园卡充值\n校园卡可通过服务大厅充值。\n\n"
        "HQ-02 宿舍报修\n一般维修通过校园服务移动端提交。"
    ).encode()
    auth = headers("admin")
    uploaded = upload(client, auth, filename="services.txt", content=content, title="校园服务").json()
    client.app.state.ingestion.wait_idle()
    document = client.get(f"/api/admin/documents/{uploaded['id']}", headers=auth).json()
    assert document["status"] == "ready"
    assert document["chunk_count"] == 2


def test_supported_office_and_pdf_parsers_preserve_section_ids(tmp_path):
    parser = UniversalDocumentParser()

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "XK-01 Course selection\nChoose courses before the deadline.")
    page.insert_text((72, 120), "XK-02 Withdrawal\nWithdrawal requires approval.")
    pdf_path = tmp_path / "guide.pdf"
    pdf.save(pdf_path)
    pdf.close()

    docx = create_docx()
    docx.add_heading("JY-01 Registration", level=1)
    docx.add_paragraph("Students must register on time.")
    docx.add_heading("JY-02 Credits", level=1)
    docx.add_paragraph("Students may take between 18 and 30 credits.")
    docx_path = tmp_path / "rules.docx"
    docx.save(docx_path)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["FAQ_ID", "Question", "Answer"])
    sheet.append(["FAQ-001", "Where is the library?", "East campus."])
    sheet.append(["FAQ-002", "When is lunch?", "From 11:00."])
    xlsx_path = tmp_path / "faq.xlsx"
    workbook.save(xlsx_path)

    csv_path = tmp_path / "faq.csv"
    csv_path.write_text("FAQ_ID,Question,Answer\nFAQ-003,Card lost?,Report it immediately.\n", encoding="utf-8")

    assert [section.section_id for section in parser.parse(pdf_path)] == ["XK-01", "XK-02"]
    assert [section.section_id for section in parser.parse(docx_path)] == ["JY-01", "JY-02"]
    assert [section.section_id for section in parser.parse(xlsx_path)] == ["FAQ-001", "FAQ-002"]
    assert [section.section_id for section in parser.parse(csv_path)] == ["FAQ-003"]


def test_batch_upload_partial_success(client, headers):
    auth = headers("admin")
    response = client.post(
        "/api/admin/documents/batch",
        headers=auth,
        files=[
            ("files", ("first.txt", "# First\nCampus library.", "text/plain")),
            ("files", ("second.md", "# Second\nCampus card.", "text/markdown")),
            ("files", ("unsupported.exe", b"bad", "application/octet-stream")),
        ],
        data={"category": "后勤"},
    )
    assert response.status_code == 202
    result = response.json()
    assert result["total"] == 3
    assert result["accepted"] == 2
    assert result["rejected"] == 1
    assert [item["success"] for item in result["items"]] == [True, True, False]
    client.app.state.ingestion.wait_idle()


def test_automatic_classification_and_manual_override(client, headers):
    auth = headers("admin")
    uploaded = upload(
        client,
        auth,
        filename="exam-rules.md",
        content="# JY-01 考试安排\n考试与成绩管理由教务系统负责。".encode(),
        title="考试与成绩管理办法",
        category="自动",
    ).json()
    assert uploaded["category"] == "教务"
    client.app.state.ingestion.wait_idle()
    detail = client.get(f"/api/admin/documents/{uploaded['id']}", headers=auth).json()
    assert detail["chunks"][0]["section_id"] == "JY-01"
    assert detail["chunks"][0]["content"].startswith("JY-01")

    updated = client.patch(
        f"/api/admin/documents/{uploaded['id']}",
        headers=auth,
        json={"category": "学工"},
    )
    assert updated.status_code == 200
    assert updated.json()["category"] == "学工"
    reindexed = client.post(f"/api/admin/documents/{uploaded['id']}/reindex", headers=auth)
    client.app.state.ingestion.wait_idle()
    assert client.get(f"/api/admin/documents/{uploaded['id']}", headers=auth).json()["category"] == "学工"

    renamed = client.patch(
        f"/api/admin/documents/{uploaded['id']}",
        headers=auth,
        json={"title": "  考试与成绩管理（修订）  "},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "考试与成绩管理（修订）"
    assert client.patch(
        f"/api/admin/documents/{uploaded['id']}",
        headers=auth,
        json={"title": "   "},
    ).status_code == 422


def test_disable_enable_reindex_and_delete(client, headers, settings):
    auth = headers("admin")
    uploaded = upload(
        client,
        auth,
        filename="life.md",
        content="# 宿舍\n宿舍报修请联系后勤平台。\n\n# 校园卡\n校园卡遗失后应立即挂失。".encode(),
        title="校园生活",
        category="后勤",
    ).json()
    document_id = uploaded["id"]
    client.app.state.ingestion.wait_idle()
    ready = client.get(f"/api/admin/documents/{document_id}", headers=auth).json()
    original_version = ready["index_version"]

    disabled = client.post(f"/api/admin/documents/{document_id}/disable", headers=auth)
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
    enabled = client.post(f"/api/admin/documents/{document_id}/enable", headers=auth)
    assert enabled.status_code == 200 and enabled.json()["status"] == "ready"

    reindex = client.post(f"/api/admin/documents/{document_id}/reindex", headers=auth)
    assert reindex.status_code == 202 and reindex.json()["status"] == "pending"
    client.app.state.ingestion.wait_idle()
    updated = client.get(f"/api/admin/documents/{document_id}", headers=auth).json()
    assert updated["status"] == "ready"
    assert updated["index_version"] != original_version

    stored_file = next(settings.upload_dir.iterdir())
    assert stored_file.exists()
    assert client.delete(f"/api/admin/documents/{document_id}", headers=auth).status_code == 204
    assert not stored_file.exists()
    assert client.get(f"/api/admin/documents/{document_id}", headers=auth).status_code == 404


def test_jwt_does_not_override_current_database_role(client, application, headers):
    auth = headers("admin")
    with application.state.database.session_factory() as session, session.begin():
        UserRepository(session).get_by_username("root").role = "student"
    assert client.get("/api/admin/documents", headers=auth).status_code == 403


@pytest.mark.parametrize("category", ["invalid"])
def test_upload_rejects_invalid_category(client, headers, category):
    assert upload(client, headers("admin"), category=category).status_code == 422
