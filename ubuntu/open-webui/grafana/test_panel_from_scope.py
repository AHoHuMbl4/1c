#!/usr/bin/env python3
"""Замки сборщика панели: касты, условие, отказ на опасном тексте, место панели.

Запуск: python3 ubuntu/open-webui/grafana/test_panel_from_scope.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import panel_from_scope as ps  # noqa: E402

SRC = "accumulationregister_реализациятмц_recordtype"
DS = {"type": "postgres", "uid": "uid1"}


class BuildSql(unittest.TestCase):
    def test_дни_касты_обязательны(self):
        sql, fmt, kind = ps.build_sql({"src": SRC, "measure": "Сумма"})
        self.assertIn('"Period"::timestamp', sql)
        self.assertIn('sum("Сумма"::DECIMAL)', sql)
        self.assertEqual((fmt, kind), ("time_series", "timeseries"))

    def test_ось_даёт_barchart_с_потолком_показа(self):
        sql, fmt, kind = ps.build_sql({"src": SRC, "measure": "Сумма",
                                       "axis": "Номенклатура"})
        self.assertEqual(kind, "barchart")
        self.assertIn('"Номенклатура"::VARCHAR', sql)
        self.assertIn(f"LIMIT {ps.AXIS_ROWS}", sql)

    def test_условие_из_scope_попадает_в_запрос(self):
        sql, _, _ = ps.build_sql({"src": SRC, "measure": "Сумма",
                                  "where": "doc_date >= '2026-08-01'"})
        self.assertIn("WHERE doc_date >= '2026-08-01'", sql)

    def test_без_условия_нет_пустого_where(self):
        sql, _, _ = ps.build_sql({"src": SRC, "measure": "Сумма", "where": "  "})
        self.assertNotIn("WHERE", sql)

    def test_итог_одним_числом(self):
        sql, fmt, kind = ps.build_sql({"src": SRC, "measure": "Сумма", "kind": "stat"})
        self.assertEqual((fmt, kind), ("table", "stat"))
        self.assertNotIn("GROUP BY", sql)

    def test_пустая_величина_отказ(self):
        with self.assertRaises(ps.SpecError):
            ps.build_sql({"src": SRC, "measure": ""})

    def test_точка_с_запятой_отказ(self):
        for spec in ({"src": f"{SRC}; DROP TABLE x", "measure": "Сумма"},
                     {"src": SRC, "measure": 'Сумма"'},
                     {"src": SRC, "measure": "Сумма", "where": "1=1; DELETE FROM x"},
                     {"src": SRC, "measure": "Сумма", "where": "1=1 -- хвост"}):
            with self.assertRaises(ps.SpecError):
                ps.build_sql(spec)

    def test_неизвестный_вид_отказ(self):
        with self.assertRaises(ps.SpecError):
            ps.build_sql({"src": SRC, "measure": "Сумма", "kind": "piechart"})


class MakePanel(unittest.TestCase):
    def test_панель_несёт_запрос_и_datasource(self):
        panel = ps.make_panel({"src": SRC, "measure": "Сумма", "title": "Продажи"},
                              DS, panel_id=7, y=18)
        self.assertEqual(panel["id"], 7)
        self.assertEqual(panel["gridPos"]["y"], 18)
        self.assertEqual(panel["datasource"], DS)
        self.assertEqual(panel["targets"][0]["datasource"], DS)
        self.assertIn("sum(", panel["targets"][0]["rawSql"])
        self.assertEqual(panel["title"], "Продажи")

    def test_разрез_говорит_о_потолке_в_заголовке(self):
        panel = ps.make_panel({"src": SRC, "measure": "Сумма", "axis": "Склад",
                               "title": "По складам"}, DS, 1, 0)
        self.assertIn(str(ps.AXIS_ROWS), panel["title"])

    def test_без_заголовка_берётся_величина(self):
        panel = ps.make_panel({"src": SRC, "measure": "Сумма"}, DS, 1, 0)
        self.assertEqual(panel["title"], "Сумма")


if __name__ == "__main__":
    unittest.main(verbosity=2)
