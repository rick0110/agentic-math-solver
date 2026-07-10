from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from typing import Any

_OCR_READER: Any = None
_OCR_LOCK = threading.Lock()

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
_TEXT_EXTS = {".txt", ".md"}

_NUMBERED_PATTERN = re.compile(
    r"(?im)^[ \t]*(?:(\d{1,3})[\.\)]|quest(?:ã|a)o[ \t]*(\d{1,3})|exerc(?:í|i)cio[ \t]*(\d{1,3})|problema[ \t]*(\d{1,3}))[ \t]*[:.\-]?[ \t]*"
)


def _get_ocr_reader() -> Any:
    global _OCR_READER
    if _OCR_READER is None:
        with _OCR_LOCK:
            if _OCR_READER is None:
                import easyocr
                import torch

                _OCR_READER = easyocr.Reader(["pt", "en"], gpu=torch.cuda.is_available())
    return _OCR_READER


def _ocr_image_bytes(data: bytes) -> str:
    reader = _get_ocr_reader()
    lines = reader.readtext(data, detail=0, paragraph=True)
    return "\n".join(lines)


def _extract_pdf_text(data: bytes) -> str:
    import fitz  # pymupdf
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages_text = []
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if len(text) < 20:
                try:
                    pixmap = doc[index].get_pixmap(dpi=200)
                    text = _ocr_image_bytes(pixmap.tobytes("png"))
                except Exception as exc:
                    text = f"[Falha ao processar página {index + 1} via OCR: {exc}]"
            pages_text.append(text)
        return "\n\n".join(pages_text)
    finally:
        doc.close()


def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(data)
    if ext in _IMAGE_EXTS:
        return _ocr_image_bytes(data)
    if ext in _TEXT_EXTS:
        return data.decode("utf-8", errors="ignore")
    raise ValueError(f"Formato de arquivo não suportado para lista: {ext}")


def split_into_problems(text: str) -> list[str]:
    """Regex-based split by numbered items. Returns [text] (single blob) when no
    reliable numbering is found, so the caller can fall back to an LLM split."""
    text = text.strip()
    if not text:
        return []

    matches = list(_NUMBERED_PATTERN.finditer(text))
    ordered_matches = []
    last_num = 0
    for match in matches:
        num = int(next(group for group in match.groups() if group))
        if num < last_num:
            continue
        ordered_matches.append(match)
        last_num = num

    if len(ordered_matches) < 2:
        return [text]

    segments = []
    for i, match in enumerate(ordered_matches):
        start = match.end()
        end = ordered_matches[i + 1].start() if i + 1 < len(ordered_matches) else len(text)
        statement = text[start:end].strip()
        if statement:
            segments.append(statement)
    return segments if len(segments) >= 2 else [text]


def llm_split_problems(text: str, client: Any, *, max_tokens: int = 4096) -> list[str]:
    """Fallback splitter for lists without clean numbering: asks the model to segment
    the raw text into individual problem statements without solving anything."""
    system_prompt = (
        "Você recebeu o texto bruto (possivelmente via OCR, com ruído) de uma lista de exercícios de matemática. "
        "Separe-o em uma lista JSON de strings, uma por enunciado de questão, na ordem em que aparecem no texto. "
        "Não resolva nada e não invente questões. Responda SOMENTE com um JSON válido (array de strings)."
    )
    response = client.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    match = re.search(r"\[.*\]", response, re.DOTALL)
    if not match:
        return [text]
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return [text]
    statements = [str(item).strip() for item in items if str(item).strip()]
    return statements or [text]
