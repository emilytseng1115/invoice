from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time

import pdfplumber
import pypdfium2 as pdfium
import requests

from invoice_extractor import InvoiceRow


@dataclass(frozen=True)
class OCRConfig:
    api_url: str
    default_model: str
    ocr_model: str
    timeout: int
    max_retries: int
    api_key_environment_variable: str


def load_ocr_config() -> OCRConfig:
    path = Path(__file__).with_name("ocr_config.json")
    values = json.loads(path.read_text(encoding="utf-8"))
    return OCRConfig(
        api_url=values["ApiUrl"],
        default_model=values["DefaultModel"],
        ocr_model=values["OCRModel"],
        timeout=int(values["Timeout"]),
        max_retries=int(values["MaxRetries"]),
        api_key_environment_variable=values["ApiKeyEnvironmentVariable"],
    )


def configured_api_key(config: OCRConfig) -> str:
    environment_key = os.getenv(config.api_key_environment_variable, "").strip().strip("()")
    if environment_key:
        return environment_key

    key_file = Path(__file__).with_name("ocr_api_key.txt")
    if key_file.exists():
        file_key = key_file.read_text(encoding="utf-8-sig").strip().strip("()")
        if file_key and file_key != "PASTE_API_KEY_HERE":
            return file_key
    return ""


def detect_image_pages(pdf_bytes: bytes) -> list[int]:
    image_pages: list[int] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            visible_text = re.sub(r"\s+", "", page.extract_text() or "")
            if len(visible_text) < 20 and bool(page.images):
                image_pages.append(page_index)
    return image_pages


def _render_page_png(pdf_bytes: bytes, page_index: int, dpi: int = 220) -> bytes:
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page = document[page_index]
        try:
            image = page.render(scale=dpi / 72).to_pil().convert("RGB")
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
        finally:
            page.close()
    finally:
        document.close()


def _extract_json(content: str) -> dict:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("OCR 回應中找不到 JSON 資料。")
    return json.loads(cleaned[start : end + 1])


def _request_ocr(image_bytes: bytes, api_key: str, config: OCRConfig) -> dict:
    image_data = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Read this commercial invoice image and return JSON only. "
        "Schema: {\"invoice_no\":\"\",\"items\":[{\"item\":\"\","
        "\"description\":\"\",\"quantity\":\"\",\"unit_price\":\"\"}]}. "
        "Item means the value below MODEL NAME, not the left-side row number. "
        "Description is the product specification aligned with that item and may span multiple lines. "
        "Keep unit_price exactly as printed; never calculate or infer it. "
        "Preserve letters, digits, punctuation, parentheses, slashes, and Chinese text."
    )
    payload = {
        "model": config.ocr_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You extract structured invoice fields accurately."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ],
            },
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error: Exception | None = None
    session = requests.Session()
    # The OCR endpoint is an internal service. Do not inherit unrelated system
    # HTTP(S)_PROXY values, which may point to an unavailable local proxy.
    session.trust_env = False
    try:
        for attempt in range(config.max_retries):
            try:
                response = session.post(
                    config.api_url,
                    headers=headers,
                    json=payload,
                    timeout=config.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"OCR service returned {response.status_code}")
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return _extract_json(content)
            except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt + 1 < config.max_retries:
                    time.sleep(min(2 ** attempt, 8))
    finally:
        session.close()

    raise RuntimeError(f"OCR 服務在重試後仍失敗：{last_error}")


def ocr_invoice_pages(
    pdf_bytes: bytes,
    page_indexes: list[int],
    api_key: str,
    config: OCRConfig | None = None,
) -> list[InvoiceRow]:
    settings = config or load_ocr_config()
    clean_key = api_key.strip().strip("()")
    if not clean_key:
        raise ValueError("請輸入 OCR API Key。")

    rows: list[InvoiceRow] = []
    current_invoice_no = "待確認"
    for page_index in page_indexes:
        result = _request_ocr(_render_page_png(pdf_bytes, page_index), clean_key, settings)
        invoice_no = str(result.get("invoice_no") or "").strip()
        if invoice_no:
            current_invoice_no = invoice_no
        for item in result.get("items") or []:
            rows.append(
                InvoiceRow(
                    invoice_no=current_invoice_no,
                    item=str(item.get("item") or "待確認").strip(),
                    description=str(item.get("description") or "待確認").strip(),
                    quantity=str(item.get("quantity") or "待確認").strip(),
                    unit_price=str(item.get("unit_price") or "無法辨識").strip(),
                    page_number=page_index + 1,
                    extraction_method="OCR",
                )
            )
    return rows


def ocr_invoice_images(
    images: list[tuple[str, bytes]],
    api_key: str,
    config: OCRConfig | None = None,
) -> list[InvoiceRow]:
    settings = config or load_ocr_config()
    clean_key = api_key.strip().strip("()")
    if not clean_key:
        raise ValueError("請輸入 OCR API Key。")

    rows: list[InvoiceRow] = []
    current_invoice_no = "待確認"
    for image_index, (image_name, image_bytes) in enumerate(images, start=1):
        result = _request_ocr(image_bytes, clean_key, settings)
        invoice_no = str(result.get("invoice_no") or "").strip()
        if invoice_no:
            current_invoice_no = invoice_no
        for item in result.get("items") or []:
            rows.append(
                InvoiceRow(
                    invoice_no=current_invoice_no,
                    item=str(item.get("item") or "待確認").strip(),
                    description=str(item.get("description") or "待確認").strip(),
                    quantity=str(item.get("quantity") or "待確認").strip(),
                    unit_price=str(item.get("unit_price") or "無法辨識").strip(),
                    page_number=image_index,
                    extraction_method=f"Word 圖片 OCR ({image_name})",
                )
            )
    return rows
