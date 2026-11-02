import pytest

from app.models import Chunk, Document
from app.services.vector_index import RetrievalResult, VectorIndexService


RETRIEVAL_REQUESTS = [
    ("GET", "/api/admin/retrieval/status", None),
    ("POST", "/api/admin/retrieval/search", {"question": "校园卡怎么补办？", "limit": 5}),
    ("POST", "/api/admin/retrieval/rebuild", {"profile": "qwen-0.6b"}),
    ("POST", "/api/admin/retrieval/switch", {"profile": "bge-small"}),
]


@pytest.mark.parametrize("method,path,payload", RETRIEVAL_REQUESTS)
def test_retrieval_routes_require_admin(client, headers, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401
    assert client.request(method, path, headers=headers(), json=payload).status_code == 403
    assert client.request(method, path, headers=headers("admin"), json=payload).status_code == 503


def test_retrieval_deduplicates_equivalent_faq_rows():
    first_document = Document(
        id=1,
        document_code="DOC-1",
        title="FAQ XLSX",
        category="后勤",
        original_name="faq.xlsx",
        stored_path="faq.xlsx",
        sha256="1" * 64,
        status="ready",
        index_version="v1",
    )
    second_document = Document(
        id=2,
        document_code="DOC-2",
        title="FAQ CSV",
        category="后勤",
        original_name="faq.csv",
        stored_path="faq.csv",
        sha256="2" * 64,
        status="ready",
        index_version="v1",
    )
    first_chunk = Chunk(
        id=10,
        document_id=1,
        index_version="v1",
        section_id="FAQ-001",
        chunk_index=0,
        content="工作表：FAQ问答\nFAQ_ID：FAQ-001\n问题：宿舍漏水怎么办？\n答案：紧急情况拨打6100。\n启用：是",
    )
    second_chunk = Chunk(
        id=11,
        document_id=2,
        index_version="v1",
        section_id="FAQ-001",
        chunk_index=0,
        content="CSV 表格\nFAQ_ID：FAQ-001\n问题：宿舍漏水怎么办？\n答案：紧急情况拨打6100。\n启用：True",
    )
    distinct_chunk = Chunk(
        id=12,
        document_id=1,
        index_version="v1",
        section_id="FAQ-002",
        chunk_index=0,
        content="问题：校园卡如何补办？答案：携带身份证到服务大厅。",
    )
    candidates = [
        RetrievalResult(first_chunk, first_document, 0.03, 0.8, 5.0),
        RetrievalResult(second_chunk, second_document, 0.029, 0.79, 4.8),
        RetrievalResult(distinct_chunk, first_document, 0.025, 0.7, 4.0),
    ]
    deduplicated = VectorIndexService._deduplicate_results(candidates, 5)
    assert [result.chunk.id for result in deduplicated] == [10, 12]
