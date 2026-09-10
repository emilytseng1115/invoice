from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from statistics import median
import re

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class Match:
    page_index: int
    x0: float
    top: float
    x1: float
    bottom: float
    baseline: float
    font_size: float

    @property
    def page_number(self) -> int:
        return self.page_index + 1


def _overlaps(char: dict, box: dict) -> bool:
    return not (
        char["x1"] < box["x0"]
        or char["x0"] > box["x1"]
        or char["bottom"] < box["top"]
        or char["top"] > box["bottom"]
    )


def _match_from_box(page, page_index: int, box: dict) -> Match:
    chars = [char for char in page.chars if _overlaps(char, box)]
    sizes = [float(char.get("size", 12)) for char in chars]
    baselines = [
        float(char["matrix"][5])
        for char in chars
        if char.get("matrix") and len(char["matrix"]) >= 6
    ]
    font_size = median(sizes) if sizes else 12.0
    baseline = median(baselines) if baselines else page.height - box["bottom"] + font_size * 0.28
    return Match(
        page_index=page_index,
        x0=float(box["x0"]),
        top=float(box["top"]),
        x1=float(box["x1"]),
        bottom=float(box["bottom"]),
        baseline=baseline,
        font_size=font_size,
    )


def find_matches(pdf_bytes: bytes, text: str) -> list[Match]:
    query = text.strip()
    if not query:
        return []

    matches: list[Match] = []
    # PDF generators often store spaces and punctuation as separate glyphs.
    # Allow invisible whitespace between every visible query character.
    pattern = r"\s*".join(re.escape(char) for char in query if not char.isspace())
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            for box in page.search(pattern, regex=True, case=False) or []:
                matches.append(_match_from_box(page, page_index, box))
    return matches


def _font_name(text: str) -> str:
    if all(ord(char) < 256 for char in text):
        return "Helvetica"
    try:
        pdfmetrics.getFont("MSung-Light")
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def edit_pdf(
    pdf_bytes: bytes,
    anchors: Match | list[Match],
    new_text: str,
    *,
    mode: str = "append",
    replace_text: str = "",
    x_offset: float = 0,
    y_offset: float = 0,
    font_size: float | None = None,
    cover_width: float = 80,
) -> bytes:
    if not new_text:
        raise ValueError("請輸入要加入的文字。")
    if mode not in {"append", "replace"}:
        raise ValueError("不支援的修改模式。")

    target_anchors = [anchors] if isinstance(anchors, Match) else list(anchors)
    if not target_anchors:
        raise ValueError("沒有可修改的欄位位置。")

    source_reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.clone_document_from_reader(source_reader)

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for anchor in target_anchors:
            source_page = pdf.pages[anchor.page_index]
            page_height = float(source_page.height)
            page_width = float(source_page.width)
            size = float(font_size or anchor.font_size)
            baseline = anchor.baseline + float(y_offset)
            x = anchor.x1 + max(2.5, size * 0.3) + float(x_offset)
            target_box = None

            if mode == "replace":
                replacement = replace_text.strip()
                if not replacement:
                    raise ValueError("取代模式需要輸入原有文字，例如 N/A。")
                candidates = source_page.search(replacement, regex=False, case=False) or []
                same_line = [
                    box
                    for box in candidates
                    if box["x0"] >= anchor.x1 - 1
                    and abs(float(box["top"]) - anchor.top) <= max(4, anchor.font_size * 0.6)
                ]
                if not same_line:
                    raise ValueError(
                        f"第 {anchor.page_number} 頁的指定欄位後方找不到要取代的原有文字。"
                    )
                target_box = min(same_line, key=lambda box: box["x0"])
                target = _match_from_box(source_page, anchor.page_index, target_box)
                x = target.x0 + float(x_offset)
                baseline = target.baseline + float(y_offset)

            overlay_buffer = BytesIO()
            overlay = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

            if mode == "replace" and target_box is not None:
                left = float(target_box["x0"]) - 1
                top = float(target_box["top"]) - 1
                detected_width = float(target_box["x1"] - target_box["x0"]) + 3
                width = max(detected_width, float(cover_width))
                height = float(target_box["bottom"] - target_box["top"]) + 3
                overlay.setFillColorRGB(1, 1, 1)
                overlay.rect(left, page_height - top - height, width, height, fill=1, stroke=0)

            overlay.setFillColorRGB(0, 0, 0)
            overlay.setFont(_font_name(new_text), size)
            overlay.drawString(x, baseline, new_text)
            overlay.save()

            overlay_buffer.seek(0)
            overlay_page = PdfReader(overlay_buffer).pages[0]
            writer.pages[anchor.page_index].merge_page(overlay_page)

    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    PdfReader(BytesIO(result))
    return result
