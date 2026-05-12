from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class VectorStore:
    """封装 LanceDB，为每种记忆类型维护独立的向量表。"""

    def __init__(self, vault_path: Path):
        self.db_path = vault_path / "_vectors"
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = None

    @property
    def db(self):
        if self._db is None:
            try:
                import lancedb
                self._db = lancedb.connect(str(self.db_path))
            except ImportError:
                raise ImportError("lancedb 未安装。运行 pip install lancedb")
        return self._db

    def _table_name(self, memory_type: str) -> str:
        return f"memory_{memory_type}"

    async def upsert(self, table: str, records: list[dict]) -> None:
        tbl_name = self._table_name(table)
        import pyarrow as pa
        batch = pa.RecordBatch.from_pylist(records)
        if tbl_name in self.db.table_names():
            tbl = self.db.open_table(tbl_name)
            tbl.delete(f"memory_id IN ({','.join(repr(r['memory_id']) for r in records)})")
            tbl.add(batch)
        else:
            self.db.create_table(tbl_name, batch)

    async def search(
        self, table: str, query_vector, top_k: int = 10, where: str | None = None,
    ) -> list[dict]:
        tbl_name = self._table_name(table)
        if tbl_name not in self.db.table_names():
            return []
        tbl = self.db.open_table(tbl_name)
        query = tbl.search(query_vector).limit(top_k)
        if where:
            query = query.where(where)
        results = query.to_list()
        return results

    async def delete(self, table: str, memory_ids: list[str]) -> None:
        tbl_name = self._table_name(table)
        if tbl_name not in self.db.table_names():
            return
        tbl = self.db.open_table(tbl_name)
        ids_str = ", ".join(repr(mid) for mid in memory_ids)
        tbl.delete(f"memory_id IN ({ids_str})")

    async def count(self, table: str, where: str | None = None) -> int:
        tbl_name = self._table_name(table)
        if tbl_name not in self.db.table_names():
            return 0
        tbl = self.db.open_table(tbl_name)
        if where:
            return len(tbl.search().where(where).to_list())
        return tbl.count_rows()

    async def list_ids(self, table: str) -> set[str]:
        tbl_name = self._table_name(table)
        if tbl_name not in self.db.table_names():
            return set()
        tbl = self.db.open_table(tbl_name)
        rows = tbl.to_lance().to_table(columns=["memory_id"]).to_pylist()
        return {r["memory_id"] for r in rows}
