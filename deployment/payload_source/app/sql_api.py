from __future__ import annotations

import json
import re
from typing import Any

import requests


SQL_API_URL = "https://srm.ecs.com.tw:8017/F83/T1"
ITEM_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class SqlApiError(RuntimeError):
    pass


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


def query_description(segment1: str, timeout: float = 30.0) -> str:
    segment1 = segment1.strip()
    if not ITEM_PATTERN.fullmatch(segment1):
        raise SqlApiError(f"Item 格式不合法：{segment1}")

    sql = (
        "select description from apps.mtl_system_items "
        f"where segment1 = '{segment1}' and organization_id = 1"
    )

    try:
        with requests.Session() as session:
            # The app must connect to the internal SQL API directly.  Do not
            # inherit machine-level HTTP(S)_PROXY values intended for other
            # network traffic.
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
            message = error.get("message") or error.get("error") if isinstance(error, dict) else str(error)
        except ValueError:
            message = response.text.strip() or "未知錯誤"
        raise SqlApiError(f"API 回傳 {response.status_code}：{message}")

    rows = _decode_rows(response)
    if not rows:
        return "查無資料"

    first_row = rows[0]
    for key, value in first_row.items():
        if key.lower() == "description":
            return str(value).strip() or "查無資料"
    return "查無資料"
