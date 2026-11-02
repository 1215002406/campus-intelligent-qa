import re
from pathlib import Path

from app.ingestion.contracts import ChunkDraft, ParsedSection

SECTION_IDENTIFIER = re.compile(r"^([A-Z]{2,}[A-Z0-9]*-\d+)(?:\s|[：:、.]|$)", re.IGNORECASE)


class UnsupportedDocumentError(ValueError):
    pass


class TextDocumentParser:
    def parse(self, path: Path) -> list[ParsedSection]:
        if path.suffix.lower() not in {".txt", ".md", ".markdown"}:
            raise UnsupportedDocumentError("当前仅支持 TXT 和 Markdown 文档")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocumentError("文档必须使用 UTF-8 编码") from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise UnsupportedDocumentError("文档没有可提取的文本")

        if path.suffix.lower() in {".md", ".markdown"}:
            sections = self._markdown_sections(text)
        else:
            sections = self._text_sections(text)
        if not sections:
            raise UnsupportedDocumentError("文档没有可用的章节内容")
        return sections

    def _markdown_sections(self, text: str) -> list[ParsedSection]:
        heading = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
        grouped: list[tuple[str, str]] = []
        title = ""
        lines: list[str] = []

        def flush() -> None:
            body = "\n".join(lines).strip()
            if body:
                grouped.append((title, body))
            lines.clear()

        for line in text.splitlines():
            match = heading.match(line)
            if match:
                flush()
                title = match.group(1).strip()
            else:
                lines.append(line)
        flush()
        coded = [item for item in grouped if self._section_id(item[0])]
        selected = coded or grouped
        return [
            ParsedSection(
                section_id=self._section_id(heading_text) or f"SEC-{index:03d}",
                text=f"{heading_text}\n{body}" if heading_text else body,
            )
            for index, (heading_text, body) in enumerate(selected, start=1)
        ]

    def _text_sections(self, text: str) -> list[ParsedSection]:
        chapter = re.compile(
            r"^(?:第[一二三四五六七八九十百千万零〇\d]+[章节篇]"
            r"|[一二三四五六七八九十]+、"
            r"|[A-Z]{2,}[A-Z0-9]*-\d+[：:、.]?\s*\S"
            r"|\d+(?:\.\d+){0,3}[、.．]\s*\S).*$"
        )
        grouped: list[tuple[str | None, str]] = []
        heading_text: str | None = None
        current: list[str] = []

        def flush() -> None:
            body = "\n".join(current).strip()
            if body:
                grouped.append((heading_text, body))
            current.clear()

        for line in text.splitlines():
            stripped = line.strip()
            if chapter.match(stripped):
                flush()
                heading_text = stripped
            current.append(line)
        flush()
        coded = [item for item in grouped if item[0] and self._section_id(item[0])]
        selected = coded or grouped
        return [
            ParsedSection(
                section_id=self._section_id(heading_text) or f"SEC-{index:03d}",
                text=body,
            )
            for index, (heading_text, body) in enumerate(selected, start=1)
        ]

    @staticmethod
    def _section_id(value: str) -> str | None:
        match = SECTION_IDENTIFIER.match(value.strip())
        if not match:
            return None
        identifier = match.group(1).upper()
        return None if identifier.split("-", 1)[0] in {"SEC", "SHEET", "ROW"} else identifier


class CharacterTextChunker:
    rule_id = "char-500-overlap-80-v1"

    def __init__(self, chunk_size: int = 500, overlap: int = 80):
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Invalid chunk size or overlap")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, sections: list[ParsedSection]) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        for section in sections:
            text = section.text.strip()
            start = 0
            chunk_index = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                if end < len(text):
                    boundary = self._find_boundary(text, start, end)
                    if boundary is not None:
                        end = boundary
                content = text[start:end].strip()
                if content:
                    chunks.append(ChunkDraft(
                        section_id=section.section_id,
                        chunk_index=chunk_index,
                        content=content,
                        page_start=section.page_start,
                        page_end=section.page_end,
                    ))
                    chunk_index += 1
                if end >= len(text):
                    break
                start = max(end - self.overlap, start + 1)
        return chunks

    @staticmethod
    def _find_boundary(text: str, start: int, end: int) -> int | None:
        minimum = start + 300
        for separator in ("\n\n", "\n", "。", "；"):
            position = text.rfind(separator, minimum, end)
            if position >= minimum:
                return position + len(separator)
        return None
