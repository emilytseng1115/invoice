from __future__ import annotations

import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import streamlit as st

from docx_extractor import extract_docx_images, extract_docx_invoice_rows
from docx_editor import edit_docx, find_word_matches
from invoice_extractor import extract_invoice_rows
from ocr_client import (
    configured_api_key,
    detect_image_pages,
    load_ocr_config,
    ocr_invoice_images,
    ocr_invoice_pages,
)
from pdf_editor import edit_pdf, find_matches
from sql_api import EcsItemLookup, SqlApiError, query_description, query_ecs_item


LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
APP_LOG = LOG_DIR / "app.log"
logger = logging.getLogger("pdf_field_editor")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(APP_LOG, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)


def report_error(title: str, exc: Exception, *, context: str = "") -> None:
    """Show a useful error to the user and retain the full traceback locally."""
    error_id = uuid4().hex[:8].upper()
    logger.exception("error_id=%s context=%s error=%s", error_id, context, exc)
    st.error(f"{title}（錯誤編號：{error_id}）")
    with st.expander("查看錯誤詳情與處理建議"):
        st.code(f"{type(exc).__name__}: {exc}", language="text")
        st.caption(f"完整例外已寫入：{APP_LOG}")
        st.markdown("請先確認檔案未損壞、未加密且格式正確；若仍失敗，請提供錯誤編號與 app.log。")


def log_event(message: str, **details: object) -> None:
    suffix = " ".join(f"{key}={value!r}" for key, value in details.items())
    logger.info("%s%s", message, f" | {suffix}" if suffix else "")


st.set_page_config(page_title="PDF／Word 發票處理工具", page_icon="✎", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f6f7fb; }
    .block-container { max-width: 1240px; padding-top: 2.2rem; }
    [data-testid="stFileUploader"] { background: white; border-radius: 16px; padding: 12px; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #e7e9f0; padding: 14px; border-radius: 14px; }
    [data-testid="stDataFrame"] { background: white; border-radius: 14px; overflow: hidden; }
    .app-hero { padding: 22px 26px; border-radius: 20px; color: white;
      background: linear-gradient(120deg, #183153, #2563eb 58%, #06b6d4);
      box-shadow: 0 14px 34px rgba(37,99,235,.18); margin-bottom: 18px; }
    .app-hero h1 { margin: 0 0 6px; font-size: 1.75rem; }
    .app-hero p { margin: 0; opacity: .9; }
    .status-ready { display:inline-flex; align-items:center; gap:8px; padding:7px 12px;
      border-radius:999px; background:#dcfce7; color:#166534; font-weight:700; font-size:.86rem; }
    .status-ready:before { content:''; width:8px; height:8px; border-radius:50%; background:#22c55e;
      box-shadow:0 0 0 4px rgba(34,197,94,.15); }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_invoice_data(file_bytes: bytes, is_pdf: bool) -> None:
    st.subheader("發票內容")
    st.caption("Invoice No、Vendor Item 與每一筆 ECS Item 顯示在同一列，並標示資料來源。")

    try:
        with st.status("正在分析文件結構…", expanded=True) as status:
            status.write("檢查文字層、表格與影像內容")
            ocr_config = load_ocr_config()
            image_pages = detect_image_pages(file_bytes) if is_pdf else []
            word_images = extract_docx_images(file_bytes) if not is_pdf else []
            word_rows = extract_docx_invoice_rows(file_bytes) if not is_pdf else []
            status.update(label="文件結構分析完成", state="complete", expanded=False)
    except Exception as exc:
        report_error("無法分析文件結構", exc, context="document preflight")
        return
    needs_word_ocr = bool(word_images) and not word_rows
    ocr_api_key = ""
    if image_pages or needs_word_ocr:
        if image_pages:
            page_labels = "、".join(str(page + 1) for page in image_pages)
            st.info(f"偵測到影像型頁面：第 {page_labels} 頁，將改用 OCR 服務。")
        else:
            st.info(f"Word 中找不到一般表格，偵測到 {len(word_images)} 張嵌入圖片，將改用 OCR 服務。")
        with st.expander("OCR 服務設定", expanded=not bool(configured_api_key(ocr_config))):
            ocr_api_key = st.text_input(
                "OCR API Key",
                value=configured_api_key(ocr_config),
                type="password",
                key="ocr_api_key_from_file_v2",
                help="金鑰只用於本次 OCR 請求，不會顯示於表格或紀錄檔。",
            )

    try:
        rows = extract_invoice_rows(file_bytes) if is_pdf else word_rows
        if is_pdf and image_pages and ocr_api_key:
            cache_key = hashlib.sha256(file_bytes + ocr_config.ocr_model.encode("utf-8")).hexdigest()
            if st.session_state.get("ocr_cache_key") != cache_key:
                with st.spinner("正在辨識影像型 PDF，請稍候..."):
                    st.session_state["ocr_rows"] = ocr_invoice_pages(
                        file_bytes, image_pages, ocr_api_key, ocr_config
                    )
                st.session_state["ocr_cache_key"] = cache_key
            rows.extend(st.session_state.get("ocr_rows", []))
        if needs_word_ocr and ocr_api_key:
            cache_key = hashlib.sha256(file_bytes + ocr_config.ocr_model.encode("utf-8")).hexdigest()
            if st.session_state.get("word_ocr_cache_key") != cache_key:
                with st.spinner("正在辨識 Word 內的圖片，請稍候..."):
                    st.session_state["word_ocr_rows"] = ocr_invoice_images(
                        word_images, ocr_api_key, ocr_config
                    )
                st.session_state["word_ocr_cache_key"] = cache_key
            rows.extend(st.session_state.get("word_ocr_rows", []))
        rows.sort(key=lambda row: row.page_number)
    except Exception as exc:
        report_error("無法讀取發票內容", exc, context=f"invoice extraction is_pdf={is_pdf}")
        return

    if not rows:
        if is_pdf and image_pages and not ocr_api_key:
            st.warning("請展開 OCR 服務設定並輸入 API Key，平台才能辨識影像型頁面。")
        elif needs_word_ocr and not ocr_api_key:
            st.warning("請展開 OCR 服務設定並輸入 API Key，平台才能辨識 Word 內的圖片。")
        elif not is_pdf:
            st.warning("Word 中找不到可辨識的發票表格或嵌入圖片。")
        else:
            st.warning("找不到 MODEL NAME 商品資料。")
        return

    descriptions: dict[str, str] = {}
    ecs_lookups: dict[str, EcsItemLookup] = {}
    if is_pdf:
        ecs_cache_key = f"ecs_items_{hashlib.sha256(file_bytes).hexdigest()}"
        ecs_lookups = st.session_state.get(ecs_cache_key, {})
        customer_items = list(dict.fromkeys(row.item for row in rows))
        missing_items = [item for item in customer_items if item not in ecs_lookups]
        if missing_items:
            progress = st.progress(0, text=f"準備查詢 0/{len(missing_items)} 筆 ECS 資料")
            updated = dict(ecs_lookups)
            for index, customer_item in enumerate(missing_items, start=1):
                try:
                    updated[customer_item] = query_ecs_item(customer_item)
                except SqlApiError as exc:
                    updated[customer_item] = EcsItemLookup("查詢失敗", "查詢失敗", "error")
                    logger.warning("ECS lookup failed item=%r error=%s", customer_item, exc)
                    st.warning(f"Vendor Item {customer_item}：{exc}")
                progress.progress(index / len(missing_items), text=f"查詢進度 {index}/{len(missing_items)}：{customer_item}")
            progress.empty()
            ecs_lookups = updated
            st.session_state[ecs_cache_key] = ecs_lookups
            st.success("ECS Item／Description 已自動查詢完成。")
    else:
        description_cache_key = f"sql_descriptions_{hashlib.sha256(file_bytes).hexdigest()}"
        descriptions = st.session_state.get(description_cache_key, {})
        item_values = list(dict.fromkeys(row.customer_pn for row in rows if row.customer_pn))
        missing_items = [item for item in item_values if item not in descriptions]
        if missing_items:
            progress = st.progress(0, text=f"正在查詢 Description 0/{len(missing_items)}")
            updated = dict(descriptions)
            for index, item_value in enumerate(missing_items, start=1):
                try:
                    updated[item_value] = query_description(item_value)
                except SqlApiError as exc:
                    updated[item_value] = "查詢失敗"
                    logger.warning("Description lookup failed item=%r error=%s", item_value, exc)
                    st.warning(f"Item {item_value}：{exc}")
                progress.progress(index / len(missing_items), text=f"正在查詢 Description {index}/{len(missing_items)}：{item_value}")
            progress.empty()
            descriptions = updated
            st.session_state[description_cache_key] = descriptions
            st.success("ECS Description 已自動查詢完成。")

    display_rows = [row.as_display_dict() for row in rows]
    for row, display_row in zip(rows, display_rows):
        if is_pdf:
            display_row.pop("Customer PN", None)
            lookup = ecs_lookups.get(row.item)
            display_row["Vendor Item"] = display_row.pop("Item")
            display_row["Vendor Description"] = display_row.pop("Description")
            display_row["ECS Item"] = lookup.ecs_item if lookup else "尚未查詢"
            display_row["ECS Description"] = lookup.ecs_description if lookup else "尚未查詢"
        else:
            display_row["ECS Description"] = descriptions.get(row.customer_pn, "尚未查詢")
            display_row["ECS Item"] = display_row.pop("Customer PN")
            display_row["Vendor Item"] = display_row.pop("Item")
            display_row.pop("Description", None)

    column_order = (
        ["Invoice No", "Vendor Item", "Vendor Description", "ECS Item", "ECS Description", "Quantity", "Unit Price", "來源"]
        if is_pdf
        else ["Invoice No", "Vendor Item", "ECS Item", "ECS Description", "Quantity", "Unit Price", "來源"]
    )

    st.dataframe(
        display_rows,
        column_order=column_order,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Invoice No": st.column_config.TextColumn("Invoice No", width="medium"),
            "Item": st.column_config.TextColumn("Item", width="medium"),
            "Customer PN": st.column_config.TextColumn("Customer PN", width="medium"),
            "Description": st.column_config.TextColumn("Description", width="large"),
            "Vendor Item": st.column_config.TextColumn("Vendor Item", width="medium"),
            "Vendor Description": st.column_config.TextColumn("Vendor Description", width="large"),
            "ECS Item": st.column_config.TextColumn("ECS Item", width="medium"),
            "ECS Description": st.column_config.TextColumn("ECS Description", width="large"),
            "Quantity": st.column_config.TextColumn("Quantity", width="small"),
            "Unit Price": st.column_config.TextColumn("Unit Price", width="small"),
            "來源": st.column_config.TextColumn("來源", width="small"),
        },
    )
    st.success(f"共擷取 {len(rows)} 筆商品資料。")


def render_pdf_editor(pdf_bytes: bytes, uploaded_name: str) -> None:
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("1. 指定修改內容")
        anchor_text = st.text_input("要尋找的欄位", value="SHIPMENT FROM:", help="請輸入 PDF 中已存在的文字。")
        mode_label = st.radio("處理方式", ["加入欄位後方", "取代原有文字"], horizontal=True)
        mode = "append" if mode_label == "加入欄位後方" else "replace"
        replace_text = ""
        if mode == "replace":
            replace_text = st.text_input("要取代的原有文字", value="N/A", help="必須位於指定欄位的同一行右側。")
        new_text = st.text_input("要加入的新文字", value="CHINA")

    with right:
        st.subheader("2. 選擇欄位位置")
        try:
            matches = find_matches(pdf_bytes, anchor_text) if anchor_text.strip() else []
        except Exception as exc:
            report_error("搜尋 PDF 欄位時發生錯誤", exc, context="find PDF matches")
            matches = []
        if matches:
            scope = st.radio(
                "修改範圍",
                ["只修改選取的一筆", "修改全部符合欄位"],
                horizontal=True,
                help="選擇全部時，會修改所有頁面中找到的相同欄位。",
            )
            options = {
                f"第 {index + 1} 筆｜第 {match.page_number} 頁｜座標 ({match.x0:.1f}, {match.top:.1f})": index
                for index, match in enumerate(matches)
            }
            selected_label = st.selectbox("搜尋結果", list(options))
            selected = matches[options[selected_label]]
            c1, c2 = st.columns(2)
            c1.metric("找到欄位", f"{len(matches)} 筆")
            c2.metric("選擇頁碼", f"第 {selected.page_number} 頁")
            if scope == "修改全部符合欄位":
                st.info(f"將一次修改全部 {len(matches)} 筆符合欄位。")
        else:
            selected = None
            scope = "只修改選取的一筆"
            st.warning("尚未找到指定欄位，請確認文字、空格與標點符號。")

    with st.expander("進階位置與外觀設定"):
        a, b, c = st.columns(3)
        x_offset = a.number_input("水平微調（正值向右）", value=0.0, step=0.5)
        y_offset = b.number_input("垂直微調（正值向上）", value=0.0, step=0.5)
        auto_size = selected.font_size if selected else 12.0
        font_size = c.number_input(
            "字體大小", min_value=5.0, max_value=72.0,
            value=float(round(auto_size, 1)), step=0.5
        )
        cover_width = st.number_input(
            "取代時的白色遮蓋寬度", min_value=5.0, max_value=500.0,
            value=80.0, step=5.0, disabled=mode != "replace",
            help="若原有文字後方還有內容，請縮小寬度以避免遮住其他文字。",
        )

    st.divider()
    if st.button("產生修改後的 PDF", type="primary", use_container_width=True, disabled=selected is None):
        try:
            with st.status("正在產生 PDF…", expanded=True) as status:
                status.write("驗證修改範圍與輸入內容")
                targets = matches if scope == "修改全部符合欄位" else selected
                status.write("套用文字與版面設定")
                result = edit_pdf(
                    pdf_bytes, targets, new_text.strip(), mode=mode,
                    replace_text=replace_text, x_offset=x_offset, y_offset=y_offset,
                    font_size=font_size, cover_width=cover_width,
                )
                status.write("完成輸出檔案驗證")
                status.update(label="PDF 產生完成", state="complete", expanded=False)
        except Exception as exc:
            report_error("無法完成 PDF 修改", exc, context=f"edit PDF mode={mode}")
        else:
            st.session_state["edited_pdf"] = result
            st.session_state["output_name"] = uploaded_name.rsplit(".", 1)[0] + "_edited.pdf"
            changed_count = len(matches) if scope == "修改全部符合欄位" else 1
            st.success(f"修改完成，共處理 {changed_count} 筆欄位，請下載新檔案。")

    if "edited_pdf" in st.session_state:
        st.download_button(
            "下載修改後的 PDF", data=st.session_state["edited_pdf"],
            file_name=st.session_state["output_name"], mime="application/pdf",
            type="primary", use_container_width=True,
        )


def render_word_editor(docx_bytes: bytes, uploaded_name: str) -> None:
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("1. 指定修改內容")
        anchor_text = st.text_input(
            "要尋找的欄位", value="SHIP FROM :", key="word_anchor",
            help="請輸入 Word 中已存在的文字。",
        )
        mode_label = st.radio(
            "處理方式", ["加入欄位後方", "取代原有文字"],
            horizontal=True, key="word_mode",
        )
        mode = "append" if mode_label == "加入欄位後方" else "replace"
        replace_text = ""
        if mode == "replace":
            replace_text = st.text_input(
                "要取代的原有文字", value="CHINA", key="word_replace_text",
                help="若欄位值位於相鄰表格儲存格，平台也會向後尋找。",
            )
        new_text = st.text_input("要加入的新文字", value="CHINA", key="word_new_text")

    with right:
        st.subheader("2. 選擇欄位位置")
        try:
            matches = find_word_matches(docx_bytes, anchor_text) if anchor_text.strip() else []
        except Exception as exc:
            report_error("搜尋 Word 欄位時發生錯誤", exc, context="find Word matches")
            matches = []
        if matches:
            scope = st.radio(
                "修改範圍", ["只修改選取的一筆", "修改全部符合欄位"],
                horizontal=True, key="word_scope",
            )
            options = {
                f"第 {index + 1} 筆｜{match.location}｜{match.preview[:50]}": index
                for index, match in enumerate(matches)
            }
            selected_label = st.selectbox("搜尋結果", list(options), key="word_match")
            selected = matches[options[selected_label]]
            c1, c2 = st.columns(2)
            c1.metric("找到欄位", f"{len(matches)} 筆")
            c2.metric("選取位置", selected.location)
        else:
            selected = None
            scope = "只修改選取的一筆"
            st.warning("尚未找到指定欄位，請確認文字、空格與標點符號。")

    st.divider()
    if st.button(
        "產生修改後的 Word", type="primary", use_container_width=True,
        disabled=selected is None, key="generate_word",
    ):
        try:
            with st.status("正在產生 Word…", expanded=True) as status:
                status.write("驗證修改範圍與輸入內容")
                targets = matches if scope == "修改全部符合欄位" else [selected]
                status.write("套用文字修改並重新封裝文件")
                result = edit_docx(
                    docx_bytes, targets, new_text, mode=mode, replace_text=replace_text
                )
                status.update(label="Word 產生完成", state="complete", expanded=False)
        except Exception as exc:
            report_error("無法完成 Word 修改", exc, context=f"edit Word mode={mode}")
        else:
            st.session_state["edited_docx"] = result
            st.session_state["word_output_name"] = uploaded_name.rsplit(".", 1)[0] + "_edited.docx"
            st.success(f"修改完成，共處理 {len(targets)} 筆欄位，請下載新檔案。")

    if "edited_docx" in st.session_state:
        st.download_button(
            "下載修改後的 Word", data=st.session_state["edited_docx"],
            file_name=st.session_state["word_output_name"],
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary", use_container_width=True,
        )


st.markdown(
    """<div class="app-hero"><h1>PDF／Word 發票處理工具</h1>
    <p>擷取發票資料、查詢 ECS 資訊並安全修改指定欄位</p></div>""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("系統狀態")
    st.markdown('<span class="status-ready">服務運作中</span>', unsafe_allow_html=True)
    st.caption("處理全程在此平台進行，原始檔不會被覆寫。")
    st.divider()
    st.markdown("**處理流程**")
    st.markdown("1. 上傳文件\n2. 分析與擷取\n3. 查詢／修改\n4. 下載結果")
    with st.expander("診斷資訊"):
        st.caption(f"應用程式日誌：{APP_LOG}")
        st.caption("如遇錯誤，請記下畫面上的錯誤編號。")

uploaded = st.file_uploader("上傳 PDF 或 Word", type=["pdf", "docx"])
if uploaded is None:
    st.info("請先選擇一份 PDF 或 Word。原始檔不會被覆寫。")
    st.stop()

st.success(f"已載入檔案：{uploaded.name}")
file_bytes = uploaded.getvalue()
is_pdf = uploaded.name.lower().endswith(".pdf")
log_event("file uploaded", name=uploaded.name, size=len(file_bytes), kind="pdf" if is_pdf else "docx")

if not file_bytes:
    st.error("上傳的檔案是空白檔案，請重新選擇。")
    st.stop()

if is_pdf:
    data_tab, edit_tab = st.tabs(["發票內容擷取", "PDF 欄位修改"])
    with data_tab:
        render_invoice_data(file_bytes, True)
    with edit_tab:
        render_pdf_editor(file_bytes, uploaded.name)
else:
    data_tab, edit_tab = st.tabs(["發票內容擷取", "Word 欄位修改"])
    with data_tab:
        render_invoice_data(file_bytes, False)
    with edit_tab:
        render_word_editor(file_bytes, uploaded.name)
