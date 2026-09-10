from __future__ import annotations

from io import BytesIO
import re
from zipfile import ZipFile

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image

from invoice_extractor import INVOICE_PATTERN, ITEM_PATTERN, InvoiceRow, _clean_line


HEADER_ALIASES = {
    "description": ("DESCRIPTION",),
    "quantity": ("QUANTITY", "INV-QTY", "QTY"),
    "unit_price": ("UNIT PRICE", "UNITPRICE", "PRICE"),
}
DOCX_INVOICE_PATTERN = re.compile(r"\b(?:INVOICE|INV)\s*NO\.?\s*[:：]?\s*(\d+)\b", re.IGNORECASE)
CUSTOMER_PN_PATTERN = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
EXCLUDED_DESCRIPTION_PREFIXES = (
    "SO:",
    "SO :",
    "MODEL NAME",
    "HS CODE",
    "PO:",
    "PO :",
    "MADE IN CHINA",
    "PARTS",
    "PACK PART",
    "CUST PN",
    "SAY TOTAL",
)


def _iter_blocks(document: DocumentObject):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _cell_lines(text: str) -> list[str]:
    return [_clean_line(line) for line in text.splitlines() if _clean_line(line)]


def _column_indexes(table: Table) -> dict[str, int] | None:
    for row_index, row in enumerate(table.rows):
        values = [_clean_line(cell.text).upper() for cell in row.cells]
        indexes: dict[str, int] = {}
        for field, aliases in HEADER_ALIASES.items():
            for index, value in enumerate(values):
                if any(alias in value for alias in aliases):
                    indexes[field] = index
                    break
        if "description" in indexes and "quantity" in indexes:
            indexes["header_row"] = row_index
            return indexes
    return None


def _invoice_no_from_table(table: Table) -> str:
    for row in table.rows:
        unique_values: list[str] = []
        for cell in row.cells:
            value = _clean_line(cell.text)
            if value and (not unique_values or unique_values[-1] != value):
                unique_values.append(value)
        for index, value in enumerate(unique_values):
            if re.search(r"\b(?:INVOICE|INV)\s*NO\.?\b", value, re.IGNORECASE):
                direct = DOCX_INVOICE_PATTERN.search(value)
                if direct:
                    return direct.group(1)
                for following in unique_values[index + 1 :]:
                    number = re.search(r"\b\d{6,}\b", following)
                    if number:
                        return number.group(0)
    return ""


def _item_and_customer_pn(cell_text: str) -> tuple[str, str]:
    lines = _cell_lines(cell_text)
    item = ""
    item_line_index = -1

    for index, line in enumerate(lines):
        if "MODEL NAME" not in line.upper():
            continue
        candidates = [line, *lines[index + 1 : index + 4]]
        for offset, candidate in enumerate(candidates):
            match = ITEM_PATTERN.search(candidate)
            if match:
                item = match.group(0).strip()
                item_line_index = index + offset
                break
        if item:
            break

    description_candidates: list[str] = []
    for index, line in enumerate(lines):
        upper = line.upper()
        if index == item_line_index or (item and item in line):
            continue
        if any(upper.startswith(prefix) for prefix in EXCLUDED_DESCRIPTION_PREFIXES):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        description_candidates.append(line)

    if not item and description_candidates:
        # Some Word invoices place both the product code and its description
        # in the DESCRIPTION cell without a MODEL NAME label.
        item = description_candidates.pop(0)
        item_line_index = 0
    customer_pn = "待確認"
    for candidate in description_candidates:
        match = CUSTOMER_PN_PATTERN.fullmatch(candidate)
        if match:
            customer_pn = match.group(0)
            break
    return item or "待確認", customer_pn


def _customer_pn_from_following_rows(table: Table, row_index: int) -> str:
    """Find the Cust PN row belonging to the current product row."""
    for following_row in table.rows[row_index + 1 : row_index + 5]:
        values = list(
            dict.fromkeys(
                _clean_line(cell.text)
                for cell in following_row.cells
                if _clean_line(cell.text)
            )
        )
        if not any("CUST PN" in value.upper() for value in values):
            continue

        for value in values:
            for match in CUSTOMER_PN_PATTERN.finditer(value):
                return match.group(0)
        return ""
    return ""


def extract_docx_invoice_rows(docx_bytes: bytes) -> list[InvoiceRow]:
    document = Document(BytesIO(docx_bytes))
    current_invoice_no = "待確認"
    rows: list[InvoiceRow] = []
    table_number = 0

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            match = INVOICE_PATTERN.search(block.text) or DOCX_INVOICE_PATTERN.search(block.text)
            if match:
                current_invoice_no = match.group(1)
            continue

        table_number += 1
        table_text = "\n".join(cell.text for row in block.rows for cell in row.cells)
        invoice_match = INVOICE_PATTERN.search(table_text) or DOCX_INVOICE_PATTERN.search(table_text)
        if invoice_match:
            current_invoice_no = invoice_match.group(1)
        else:
            current_invoice_no = _invoice_no_from_table(block) or current_invoice_no

        indexes = _column_indexes(block)
        if not indexes:
            continue

        for row_index, row in enumerate(
            block.rows[indexes["header_row"] + 1 :],
            start=indexes["header_row"] + 1,
        ):
            cells = row.cells
            description_index = indexes["description"]
            quantity_index = indexes["quantity"]
            if max(description_index, quantity_index) >= len(cells):
                continue

            item, customer_pn = _item_and_customer_pn(cells[description_index].text)
            if item == "待確認":
                continue
            customer_pn = _customer_pn_from_following_rows(block, row_index) or customer_pn
            quantity = _clean_line(cells[quantity_index].text) or "待確認"
            if not re.search(r"\d", quantity):
                continue
            unit_price = "無法辨識"
            price_index = indexes.get("unit_price")
            if price_index is not None and price_index < len(cells):
                unit_price = _clean_line(cells[price_index].text) or "無法辨識"

            candidate = InvoiceRow(
                    invoice_no=current_invoice_no,
                    item=item,
                    description="待確認",
                    quantity=quantity,
                    customer_pn=customer_pn,
                    unit_price=unit_price,
                    page_number=table_number,
                    extraction_method="Word 表格",
                )
            signature = (
                candidate.invoice_no,
                candidate.item,
                candidate.customer_pn,
                candidate.quantity,
                candidate.unit_price,
            )
            if not any(
                (existing.invoice_no, existing.item, existing.customer_pn,
                 existing.quantity, existing.unit_price) == signature
                for existing in rows
            ):
                rows.append(candidate)

    return rows


def extract_docx_images(docx_bytes: bytes) -> list[tuple[str, bytes]]:
    """Return embedded raster images in document order for OCR fallback."""
    supported = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
    with ZipFile(BytesIO(docx_bytes)) as archive:
        names = [
            name for name in archive.namelist()
            if name.lower().startswith("word/media/") and name.lower().endswith(supported)
        ]
        images: list[tuple[str, bytes]] = []
        for name in names:
            data = archive.read(name)
            try:
                with Image.open(BytesIO(data)) as image:
                    width, height = image.size
                    if width * height < 250_000:
                        continue
                    converted = image.convert("RGB")
                    output = BytesIO()
                    converted.save(output, format="PNG", optimize=True)
                    data = output.getvalue()
            except Exception:
                continue
            images.append((name.rsplit("/", 1)[-1], data))
        return images
