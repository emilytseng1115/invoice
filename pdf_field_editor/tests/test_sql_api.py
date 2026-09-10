from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

from sql_api import SqlApiError, query_ecs_item


class QueryEcsItemTests(TestCase):
    def _response(self, rows):
        response = Mock(ok=True)
        response.json.return_value = rows
        return response

    def test_one_mapping(self):
        with patch("sql_api.requests.Session") as session_class:
            session = session_class.return_value.__enter__.return_value
            session.post.return_value = self._response(
                [{"ITEM_NO": "ECS-001", "ITEM_DESC": "ECS DESC"}]
            )
            result = query_ecs_item("15DPK-013910AS")

        self.assertEqual(result.ecs_item, "ECS-001")
        self.assertEqual(result.ecs_description, "ECS DESC")
        sql = session.post.call_args.kwargs["json"]["SQL"]
        self.assertIn("customer_item_no = '15DPK-013910AS'", sql)

    def test_no_mapping(self):
        with patch("sql_api.requests.Session") as session_class:
            session_class.return_value.__enter__.return_value.post.return_value = self._response([])
            result = query_ecs_item("15DPK-013910AS")
        self.assertEqual(result.status, "no_data")

    def test_multiple_mappings_are_not_silently_reduced(self):
        with patch("sql_api.requests.Session") as session_class:
            session_class.return_value.__enter__.return_value.post.return_value = self._response(
                [
                    {"ITEM_NO": "ECS-001", "ITEM_DESC": "DESC 1"},
                    {"ITEM_NO": "ECS-002", "ITEM_DESC": "DESC 2"},
                ]
            )
            result = query_ecs_item("15DPK-013910AS")
        self.assertEqual(result.status, "multiple")
        self.assertIn("ECS-001", result.ecs_item)
        self.assertIn("ECS-002", result.ecs_item)

    def test_rejects_sql_injection_characters(self):
        with self.assertRaises(SqlApiError):
            query_ecs_item("X' OR '1'='1")
