from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import requests


SQL_API_URL = "https://srm.ecs.com.tw:8017/F83/T1"
ITEM_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class SqlApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class EcsItemLookup:
    ecs_item: str
    ecs_description: str
    status: str


def _decode_rows(response: requests.Response) -> list[dict[str, Any]]:
    try:
        payload: Any = response.json()
        if isinstance(payload, str):
            payload = json.loads(payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SqlApiError("API 回應不是有效的 JSON") from exc

    if not isinstance(payload, list):
        raise SqlApiError("API 回應格式不正確")
    return [row for row in payload if isinstance(row, dict)]


def _row_value(row: dict[str, Any], field_name: str) -> str:
    for key, value in row.items():
        if key.lower() == field_name.lower():
            return str(value or "").strip()
    return ""


def _execute_sql(sql: str, timeout: float) -> list[dict[str, Any]]:
    try:
        with requests.Session() as session:
            # 內部 SQL API 必須直接連線，不沿用電腦上其他用途的 Proxy。
            session.trust_env = False
            response = session.post(
                SQL_API_URL,
                json={"SQL": sql},
                verify=False,
                timeout=timeout,
            )
    except requests.RequestException as exc:
        raise SqlApiError(f"API 連線失敗：{exc}") from exc

    if not response.ok:
        try:
            error = response.json()
            message = error.get("details") or error.get("message") or error.get("error") if isinstance(error, dict) else str(error)
        except ValueError:
            message = response.text.strip() or "未知錯誤"
        raise SqlApiError(f"API 回傳 {response.status_code}：{message}")

    return _decode_rows(response)


def query_description(segment1: str, timeout: float = 30.0) -> str:
    segment1 = segment1.strip()
    if not ITEM_PATTERN.fullmatch(segment1):
        raise SqlApiError(f"Item 格式不合法：{segment1}")

    sql = (
        "select description from apps.mtl_system_items "
        f"where segment1 = '{segment1}' and organization_id = 1"
    )

    rows = _execute_sql(sql, timeout)
    if not rows:
        return "查無資料"

    first_row = rows[0]
    for key, value in first_row.items():
        if key.lower() == "description":
            return str(value).strip() or "查無資料"
    return "查無資料"


def query_ecs_item(customer_item_no: str, timeout: float = 30.0) -> EcsItemLookup:
    customer_item_no = customer_item_no.strip()
    if not ITEM_PATTERN.fullmatch(customer_item_no):
        raise SqlApiError(f"Vendor Item 格式不合法：{customer_item_no}")

    sql = (
        "SELECT item_no "
        "      ,item_desc "
        "  FROM apps.mtl_customer_item_xrefs_v1 "
        f" WHERE customer_item_no = '{customer_item_no}'"
    )
    rows = _execute_sql(sql, timeout)
    if not rows:
        return EcsItemLookup("查無對應", "查無對應", "no_data")

    values: list[tuple[str, str]] = []
    for row in rows:
        pair = (_row_value(row, "item_no"), _row_value(row, "item_desc"))
        if pair not in values:
            values.append(pair)

    if len(values) == 1:
        ecs_item, ecs_description = values[0]
        return EcsItemLookup(ecs_item or "待確認", ecs_description or "待確認", "ok")

    ecs_items = "；".join(value[0] or "待確認" for value in values)
    ecs_descriptions = "；".join(value[1] or "待確認" for value in values)
    return EcsItemLookup(f"多筆：{ecs_items}", f"多筆：{ecs_descriptions}", "multiple")
