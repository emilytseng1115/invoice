from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import re

import pdfplumber


@dataclass(frozen=True)
class InvoiceRow:
    invoice_no: str
    item: str
    description: str
    quantity: str
    customer_pn: str = "待確認"
    unit_price: str = "無法辨識"
    page_number: int = 0
    extraction_method: str = "PDF 文字"

    def as_display_dict(self) -> dict[str, str]:
        values = asdict(self)
        return {
            "Invoice No": values["invoice_no"],
            "Item": values["item"],
            "Customer PN": values["customer_pn"],
            "Description": values["description"],
            "Quantity": values["quantity"],
            "Unit Price": values["unit_price"],
            "來源": values["extraction_method"],
        }


ITEM_PATTERN = re.compile(r"\b[A-Z0-9]+-[A-Z0-9-]+(?:\([^)]+\))?", re.IGNORECASE)
INVOICE_PATTERN = re.compile(r"INVOICE\s*NO\s*:\s*([A-Z0-9-]+)", re.IGNORECASE)
QUANTITY_PATTERN = re.compile(r"^\d[\d,]*$")
PRICE_PATTERN = re.compile(r"^\d[\d,]*(?:\.\d+)?$")


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _clean_description(line: str) -> str:
    wifi_index = line.upper().find("WIFI")
    value = line[wifi_index:] if wifi_index >= 0 else line
    value = re.sub(r"\s*/\s*[无無]\s*网\s*卡.*$", "", value, flags=re.IGNORECASE)
    return _clean_line(value)


def _group_words_by_line(words: list[dict], tolerance: float = 3.0) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda value: (float(value["top"]), float(value["x0"]))):
        for line in lines:
            line_top = sum(float(value["top"]) for value in line) / len(line)
            if abs(float(word["top"]) - line_top) <= tolerance:
                line.append(word)
                break
        else:
            lines.append([word])

    for line in lines:
        line.sort(key=lambda value: float(value["x0"]))
    lines.sort(key=lambda line: sum(float(value["top"]) for value in line) / len(line))
    return lines


def _join_line_words(words: list[dict]) -> str:
    result = ""
    previous = None
    for word in words:
        text = word["text"]
        if previous is None:
            result = text
        else:
            gap = float(word["x0"]) - float(previous["x1"])
            result += text if gap <= 2.5 else f" {text}"
        previous = word
    return result


def _join_description_lines(lines: list[str]) -> str:
    result = ""
    for line in lines:
        if not result:
            result = line
        elif result[-1:] and line[:1] and re.match(r"[\u3400-\u9fff]", result[-1]) and re.match(r"[\u3400-\u9fff]", line[0]):
            result += line
        else:
            result += f" {line}"
    return result


def _extract_items(lines: list[str]) -> list[str]:
    items: list[str] = []

    for index, line in enumerate(lines):
        if "MODEL NAME" not in line.upper():
            continue
        candidates = [line, *lines[index + 1 : index + 4]]
        for candidate in candidates:
            match = ITEM_PATTERN.search(candidate)
            if match:
                item = match.group(0).strip()
                if item not in items:
                    items.append(item)
                break

    return items


def _quantity_header(page) -> dict | None:
    headers = page.search("QUANTITY", regex=False, case=False) or []
    return headers[0] if headers else None


def _unit_price_header(page) -> dict | None:
    headers = page.search("UNIT PRICE", regex=False, case=False) or []
    return headers[0] if headers else None


def _item_boxes(page, items: list[str]) -> list[dict]:
    boxes: list[dict] = []
    for item in items:
        found = page.search(re.escape(item), regex=True, case=False) or []
        if found:
            boxes.append(found[0])
    return boxes


def _extract_descriptions(page, item_boxes: list[dict]) -> list[str]:
    words = page.extract_words() or []
    descriptions: list[str] = []

    for box in item_boxes:
        item_top = float(box["top"])
        minimum_x = float(box["x1"]) + 24
        description_words = [
            word
            for word in words
            if item_top - 4 <= float(word["top"]) <= item_top + 18
            and float(word["x0"]) >= minimum_x
        ]
        line_groups = _group_words_by_line(description_words)
        line_texts = [_join_line_words(line) for line in line_groups]
        description = _clean_description(_join_description_lines(line_texts))
        descriptions.append(description or "待確認")

    return descriptions


def _extract_quantities(page, item_boxes: list[dict], expected_count: int) -> list[str]:
    header = _quantity_header(page)
    if header is None:
        return ["待確認"] * expected_count

    center = (float(header["x0"]) + float(header["x1"])) / 2
    words = page.extract_words() or []
    candidates = [
        word
        for word in words
        if QUANTITY_PATTERN.fullmatch(word["text"])
        and abs(((float(word["x0"]) + float(word["x1"])) / 2) - center) <= 55
        and float(word["top"]) > float(header["bottom"])
    ]

    quantities: list[str] = []
    for box in item_boxes:
        item_top = float(box["top"])
        nearby = [word for word in candidates if item_top - 65 <= float(word["top"]) <= item_top - 4]
        if nearby:
            selected = min(nearby, key=lambda word: abs(item_top - float(word["top"])))
            quantities.append(selected["text"].replace(",", ""))
        else:
            quantities.append("待確認")

    return (quantities + ["待確認"] * expected_count)[:expected_count]


def _extract_unit_prices(page, item_boxes: list[dict], expected_count: int) -> list[str]:
    header = _unit_price_header(page)
    if header is None:
        return ["無法辨識"] * expected_count

    center = (float(header["x0"]) + float(header["x1"])) / 2
    words = page.extract_words() or []
    candidates = [
        word
        for word in words
        if PRICE_PATTERN.fullmatch(word["text"])
        and abs(((float(word["x0"]) + float(word["x1"])) / 2) - center) <= 90
        and float(word["top"]) > float(header["bottom"])
    ]

    prices: list[str] = []
    for box in item_boxes:
        item_top = float(box["top"])
        nearby = [word for word in candidates if item_top - 65 <= float(word["top"]) <= item_top - 4]
        if nearby:
            selected = min(nearby, key=lambda word: abs(item_top - float(word["top"])))
            prices.append(f"USD {selected['text']}")
        else:
            prices.append("無法辨識")

    return (prices + ["無法辨識"] * expected_count)[:expected_count]


def extract_invoice_rows(pdf_bytes: bytes) -> list[InvoiceRow]:
    current_invoice_no = "待確認"
    records: list[tuple[str, str, str, str, str, int]] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]

            # Each page may begin a different invoice. When a continuation page
            # omits the invoice number, retain the most recently detected one.
            match = INVOICE_PATTERN.search(text)
            if match:
                current_invoice_no = match.group(1)

            items = _extract_items(lines)
            item_boxes = _item_boxes(page, items)
            descriptions = _extract_descriptions(page, item_boxes)
            quantities = _extract_quantities(page, item_boxes, len(items))
            unit_prices = _extract_unit_prices(page, item_boxes, len(items))

            for index, item in enumerate(items):
                description = descriptions[index] if index < len(descriptions) else "待確認"
                quantity = quantities[index] if index < len(quantities) else "待確認"
                unit_price = unit_prices[index] if index < len(unit_prices) else "無法辨識"
                records.append((current_invoice_no, item, description, quantity, unit_price, page.page_number))

    return [
        InvoiceRow(
            invoice_no=invoice_no,
            item=item,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            page_number=page_number,
        )
        for invoice_no, item, description, quantity, unit_price, page_number in records
    ]
