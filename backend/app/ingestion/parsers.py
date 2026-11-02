import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
import pymupdf
from docx import Document as load_docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.contracts import ParsedSection
from app.ingestion.text import SECTION_IDENTIFIER, TextDocumentParser, UnsupportedDocumentError

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".markdown", ".csv"}
MAX_TABLE_ROWS = 10_000
MAX_EXTRACTED_CHARS = 5_000_000
HEADING_PATTERN = re.compile(
    r"^(?:第[一二三四五六七八九十百千万零〇\d]+[章节篇]"
    r"|[一二三四五六七八九十]+、"
    r"|[A-Z]{2,}[A-Z0-9]*-\d+[：:、.]?\s*\S"
    r"|\d+(?:\.\d+){0,3}[、.．]\s*\S)"
)


class UniversalDocumentParser:
    def __init__(self):
        self.text_parser = TextDocumentParser()

    def parse(self, path: Path) -> list[ParsedSection]:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            sections = self.text_parser.parse(path)
        elif suffix == ".pdf":
            sections = self._parse_pdf(path)
        elif suffix == ".docx":
            sections = self._parse_docx(path)
        elif suffix == ".xlsx":
            sections = self._parse_xlsx(path)
        elif suffix == ".csv":
            sections = self._parse_csv(path)
        else:
            raise UnsupportedDocumentError("不支持的文档格式")
        if not sections:
            raise UnsupportedDocumentError("文档没有可提取的文本")
        if sum(len(section.text) for section in sections) > MAX_EXTRACTED_CHARS:
            raise UnsupportedDocumentError("文档提取后的文本过长")
        return sections

    def _parse_pdf(self, path: Path) -> list[ParsedSection]:
        try:
            document = pymupdf.open(path)
        except Exception as exc:
            raise UnsupportedDocumentError("PDF 文件无法读取或已经损坏") from exc
        sections: list[ParsedSection] = []
        lines: list[str] = []
        section_id: str | None = None
        page_start: int | None = None
        page_end: int | None = None

        def flush() -> None:
            body = "\n".join(lines).strip()
            if body:
                sections.append(ParsedSection(
                    section_id=section_id or f"SEC-{len(sections) + 1:03d}",
                    text=body,
                    page_start=page_start,
                    page_end=page_end,
                ))
            lines.clear()

        try:
            for page_number, page in enumerate(document, start=1):
                for line in page.get_text("text").splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if HEADING_PATTERN.match(stripped):
                        flush()
                        section_id = self._identifier(stripped)
                        page_start = page_number
                    lines.append(stripped)
                    page_end = page_number
            flush()
        finally:
            document.close()
        coded = [section for section in sections if self._identifier(section.section_id)]
        return coded or sections

    def _parse_docx(self, path: Path) -> list[ParsedSection]:
        try:
            document = load_docx(path)
        except Exception as exc:
            raise UnsupportedDocumentError("DOCX 文件无法读取或已经损坏") from exc
        grouped: list[tuple[str | None, list[str]]] = []
        heading: str | None = None
        lines: list[str] = []

        def flush() -> None:
            body = "\n".join(current for current in lines if current.strip()).strip()
            if body:
                grouped.append((heading, body.splitlines()))
            lines.clear()

        for child in document.element.body.iterchildren():
            if child.tag.endswith("}p"):
                paragraph = Paragraph(child, document)
                text = paragraph.text.strip()
                if not text:
                    continue
                style = paragraph.style.name.lower() if paragraph.style is not None else ""
                if style.startswith("heading") or "标题" in style:
                    flush()
                    heading = text
                else:
                    lines.append(text)
            elif child.tag.endswith("}tbl"):
                table = Table(child, document)
                for row in table.rows:
                    values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    if any(values):
                        lines.append(" | ".join(values))
        flush()
        coded = [item for item in grouped if item[0] and self._identifier(item[0])]
        selected = coded or grouped
        return [
            ParsedSection(
                section_id=self._identifier(title) or f"SEC-{index:03d}",
                text="\n".join([title, *body]) if title else "\n".join(body),
            )
            for index, (title, body) in enumerate(selected, start=1)
        ]

    def _parse_xlsx(self, path: Path) -> list[ParsedSection]:
        try:
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise UnsupportedDocumentError("XLSX 文件无法读取或已经损坏") from exc
        sections: list[ParsedSection] = []
        try:
            for sheet_index, worksheet in enumerate(workbook.worksheets, start=1):
                rows: list[list[Any]] = []
                for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                    if row_index > MAX_TABLE_ROWS:
                        raise UnsupportedDocumentError(f"工作表 {worksheet.title} 行数过多")
                    rows.append(list(row))
                sections.extend(self._table_sections(
                    rows,
                    fallback_prefix=f"SHEET{sheet_index}",
                    context=f"工作表：{worksheet.title}",
                ))
        finally:
            workbook.close()
        return sections

    def _parse_csv(self, path: Path) -> list[ParsedSection]:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocumentError("CSV 文件必须使用 UTF-8 编码") from exc
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        if len(rows) > MAX_TABLE_ROWS:
            raise UnsupportedDocumentError("CSV 行数过多")
        return self._table_sections(rows, fallback_prefix="ROW", context="CSV 表格")

    def _table_sections(self, rows: list[list[Any]], *, fallback_prefix: str, context: str) -> list[ParsedSection]:
        nonempty = [[self._value(cell) for cell in row] for row in rows if any(self._value(cell) for cell in row)]
        if not nonempty:
            return []
        first = nonempty[0]
        header_like = {str(first[0]).strip().upper(), *map(str, first[:3])} & {
            "FAQ_ID", "ID", "编号", "序号", "题号",
        }
        headers = first if header_like else []
        data_rows = nonempty[1:] if header_like else nonempty
        sections: list[ParsedSection] = []
        for row_index, row in enumerate(data_rows, start=2 if header_like else 1):
            identifier = next((self._identifier(cell) for cell in row if self._identifier(cell)), None)
            pairs = []
            for cell_index, cell in enumerate(row):
                if not cell:
                    continue
                label = headers[cell_index] if cell_index < len(headers) and headers[cell_index] else f"列{cell_index + 1}"
                pairs.append(f"{label}：{cell}")
            if pairs:
                sections.append(ParsedSection(
                    section_id=identifier or f"{fallback_prefix}-{row_index:04d}",
                    text=f"{context}\n" + "\n".join(pairs),
                ))
        coded = [section for section in sections if self._identifier(section.section_id)]
        return coded or sections

    @staticmethod
    def _identifier(value: str) -> str | None:
        match = SECTION_IDENTIFIER.match(value.strip())
        if not match:
            return None
        identifier = match.group(1).upper()
        return None if identifier.split("-", 1)[0] in {"SEC", "SHEET", "ROW"} else identifier

    @staticmethod
    def _value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bool):
            return "是" if value else "否"
        return str(value).replace("\x00", "").strip()
