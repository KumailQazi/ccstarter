"""Check the SQL we generate is the SQL we mean.

DuckDB is optional here: if it is installed, the query is really executed
against a local Parquet file written by this test.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ccstarter import query  # noqa: E402


class SqlGenerationTest(unittest.TestCase):
    def test_literal_list_escapes_quotes(self):
        s = query._literal_list(["https://a/x.parquet", "https://a/o'brien.parquet"])
        self.assertIn("'https://a/x.parquet'", s)
        self.assertIn("o''brien", s)

    def test_empty_shards_raise(self):
        with self.assertRaises(query.QueryError):
            query.register_index(mock_con(), [])


def mock_con():
    class C:
        def execute(self, sql):
            C.seen = sql
            return self
        def close(self):
            pass
    return C()


class DuckDbExecutionTest(unittest.TestCase):
    def setUp(self):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            self.skipTest("duckdb not installed")
        import duckdb, tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "part.parquet")
        con = duckdb.connect()
        con.execute("CREATE TABLE t(url_host_tld VARCHAR, url_host_registered_domain VARCHAR)")
        con.execute("INSERT INTO t VALUES ('pk','a.pk'),('pk','a.pk'),('pk','b.pk'),('com','c.com')")
        con.execute(f"COPY t TO '{self.path}' (FORMAT parquet)")
        con.close()

    def test_query_returns_dataframe(self):
        df = query.run_sql(
            "SELECT url_host_registered_domain AS d, count(*) AS n FROM ccindex "
            "WHERE url_host_tld = 'pk' GROUP BY 1 ORDER BY n DESC",
            crawl="unused",
            urls=[self.path],
        )
        self.assertEqual(list(df["d"]), ["a.pk", "b.pk"])
        self.assertEqual(int(df["n"].iloc[0]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
