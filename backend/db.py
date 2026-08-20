"""SQLite storage layer with a Motor-compatible API.

Each Mongo collection is stored as its own SQLite table with a two-column
schema: `(key TEXT PRIMARY KEY, data TEXT NOT NULL)`. `data` is a JSON blob
of the full document, and `key` is derived from the document's natural
primary field for that collection (id, category, material, subtype, _id).

The public surface intentionally mirrors the subset of Motor used by
`server.py`, so route handlers can keep their existing calls unchanged:
`find_one`, `find`, `insert_one`, `update_one`, `update_many`,
`delete_one`, `delete_many`, `count_documents`, and a chained
`find(...).sort(...).to_list(n)` cursor.
"""
import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


# Natural primary key column for each collection
COLLECTION_PK: Dict[str, str] = {
    "equipment_historical": "id",
    "projects": "id",
    "equipment_rows": "id",
    "scale_exponents": "category",
    "escalation_weights": "category",
    "pressure_settings": "category",
    "material_factors": "material",
    "pump_configs": "subtype",
    "similarity_config": "_id",
}


def _match(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for k, v in query.items():
        actual = doc.get(k)
        if isinstance(v, dict) and "$in" in v:
            if actual not in v["$in"]:
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, collection: "Collection", query: Dict[str, Any]):
        self.collection = collection
        self.query = query
        self._sort: Optional[tuple] = None

    def sort(self, key: str, direction: int = 1) -> "_Cursor":
        self._sort = (key, direction)
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = await self.collection._find_matching(self.query)
        if self._sort:
            key, direction = self._sort
            reverse = direction < 0
            docs.sort(key=lambda d: (d.get(key) is None, d.get(key) or ""), reverse=reverse)
        if length is not None:
            docs = docs[:length]
        return docs


class _Result:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class Collection:
    def __init__(self, db: "Database", name: str):
        self.db = db
        self.name = name
        self.pk_field = COLLECTION_PK[name]

    async def _find_matching(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        return await self.db._find(self.name, query)

    async def find_one(self, query: Dict[str, Any], projection: Optional[Dict] = None) -> Optional[Dict]:
        docs = await self._find_matching(query)
        return docs[0] if docs else None

    def find(self, query: Optional[Dict] = None, projection: Optional[Dict] = None) -> _Cursor:
        return _Cursor(self, query or {})

    async def insert_one(self, doc: Dict[str, Any]) -> _Result:
        key = self.db._extract_key(self.name, doc)
        if key is None:
            raise ValueError(f"missing primary key for collection {self.name}")
        await self.db._write(self.name, str(key), doc)
        return _Result(inserted_id=key)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any],
                         upsert: bool = False) -> _Result:
        matched, modified = await self.db._update(self.name, query, update, upsert=upsert, multi=False)
        return _Result(matched_count=matched, modified_count=modified)

    async def update_many(self, query: Dict[str, Any], update: Dict[str, Any]) -> _Result:
        matched, modified = await self.db._update(self.name, query, update, upsert=False, multi=True)
        return _Result(matched_count=matched, modified_count=modified)

    async def delete_one(self, query: Dict[str, Any]) -> _Result:
        return _Result(deleted_count=await self.db._delete(self.name, query, multi=False))

    async def delete_many(self, query: Dict[str, Any]) -> _Result:
        return _Result(deleted_count=await self.db._delete(self.name, query, multi=True))

    async def count_documents(self, query: Dict[str, Any]) -> int:
        docs = await self._find_matching(query)
        return len(docs)


class Database:
    """SQLite database with per-collection JSON-blob tables."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._collections: Dict[str, Collection] = {}
        self.init_sync()

    # -- connection helpers ------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def init_sync(self) -> None:
        with self._lock:
            with self._conn() as c:
                for name in COLLECTION_PK:
                    c.execute(
                        f'CREATE TABLE IF NOT EXISTS "{name}" '
                        '(key TEXT PRIMARY KEY, data TEXT NOT NULL)'
                    )
                c.commit()

    # -- collection factory ------------------------------------------------
    def __getattr__(self, name: str) -> Collection:
        if name in COLLECTION_PK:
            if name not in self._collections:
                self._collections[name] = Collection(self, name)
            return self._collections[name]
        raise AttributeError(name)

    # -- internal ----------------------------------------------------------
    def _extract_key(self, name: str, doc: Dict[str, Any]) -> Optional[Any]:
        pk = COLLECTION_PK[name]
        return doc.get(pk)

    async def _write(self, name: str, key: str, doc: Dict[str, Any]) -> None:
        def _do():
            with self._lock:
                with self._conn() as c:
                    c.execute(
                        f'INSERT OR REPLACE INTO "{name}" (key, data) VALUES (?, ?)',
                        (str(key), json.dumps(doc, default=str)),
                    )
                    c.commit()
        await asyncio.to_thread(_do)

    async def _find(self, name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        pk_field = COLLECTION_PK[name]

        def _do() -> List[Dict[str, Any]]:
            with self._conn() as c:
                # Fast path: direct pk equality lookup
                if pk_field in query and not isinstance(query[pk_field], dict):
                    row = c.execute(
                        f'SELECT data FROM "{name}" WHERE key=?',
                        (str(query[pk_field]),),
                    ).fetchone()
                    if not row:
                        return []
                    doc = json.loads(row[0])
                    return [doc] if _match(doc, query) else []
                # Fast path: $in over pk
                if pk_field in query and isinstance(query[pk_field], dict) and "$in" in query[pk_field]:
                    keys = [str(k) for k in query[pk_field]["$in"]]
                    if not keys:
                        return []
                    placeholders = ",".join(["?"] * len(keys))
                    rows = c.execute(
                        f'SELECT data FROM "{name}" WHERE key IN ({placeholders})',
                        keys,
                    ).fetchall()
                    docs = [json.loads(r[0]) for r in rows]
                    return [d for d in docs if _match(d, query)]
                # Slow path: full scan + filter
                rows = c.execute(f'SELECT data FROM "{name}"').fetchall()
                docs = [json.loads(r[0]) for r in rows]
                return [d for d in docs if _match(d, query)]

        return await asyncio.to_thread(_do)

    async def _update(self, name: str, query: Dict[str, Any], update: Dict[str, Any],
                      upsert: bool, multi: bool) -> tuple:
        pk_field = COLLECTION_PK[name]

        def _do() -> tuple:
            with self._lock:
                with self._conn() as c:
                    # Load candidate rows
                    if pk_field in query and not isinstance(query[pk_field], dict):
                        row = c.execute(
                            f'SELECT key, data FROM "{name}" WHERE key=?',
                            (str(query[pk_field]),),
                        ).fetchone()
                        candidates = [row] if row else []
                    else:
                        candidates = c.execute(f'SELECT key, data FROM "{name}"').fetchall()

                    matched = 0
                    modified = 0
                    for k, dstr in candidates:
                        doc = json.loads(dstr)
                        if not _match(doc, query):
                            continue
                        matched += 1
                        if "$set" in update:
                            doc.update(update["$set"])
                        if "$unset" in update:
                            for uk in update["$unset"].keys():
                                doc.pop(uk, None)
                        if "$set" not in update and "$unset" not in update:
                            doc.update(update)
                        new_key = str(self._extract_key(name, doc) or k)
                        if new_key != k:
                            c.execute(f'DELETE FROM "{name}" WHERE key=?', (k,))
                        c.execute(
                            f'INSERT OR REPLACE INTO "{name}" (key, data) VALUES (?, ?)',
                            (new_key, json.dumps(doc, default=str)),
                        )
                        modified += 1
                        if not multi:
                            break

                    if matched == 0 and upsert:
                        # Build doc from query (excluding operator subdocs) + $set
                        doc: Dict[str, Any] = {kq: vq for kq, vq in query.items() if not isinstance(vq, dict)}
                        if "$set" in update:
                            doc.update(update["$set"])
                        if "$set" not in update and "$unset" not in update:
                            doc.update(update)
                        key = self._extract_key(name, doc)
                        if key is None:
                            raise ValueError(f"upsert into {name} requires primary key")
                        c.execute(
                            f'INSERT OR REPLACE INTO "{name}" (key, data) VALUES (?, ?)',
                            (str(key), json.dumps(doc, default=str)),
                        )
                        modified = 1

                    c.commit()
                    return matched, modified

        return await asyncio.to_thread(_do)

    async def _delete(self, name: str, query: Dict[str, Any], multi: bool) -> int:
        pk_field = COLLECTION_PK[name]

        def _do() -> int:
            with self._lock:
                with self._conn() as c:
                    if pk_field in query and not isinstance(query[pk_field], dict) and len(query) == 1:
                        r = c.execute(f'DELETE FROM "{name}" WHERE key=?', (str(query[pk_field]),))
                        c.commit()
                        return r.rowcount
                    rows = c.execute(f'SELECT key, data FROM "{name}"').fetchall()
                    to_delete: List[str] = []
                    for k, dstr in rows:
                        doc = json.loads(dstr)
                        if _match(doc, query):
                            to_delete.append(k)
                            if not multi:
                                break
                    for k in to_delete:
                        c.execute(f'DELETE FROM "{name}" WHERE key=?', (k,))
                    c.commit()
                    return len(to_delete)

        return await asyncio.to_thread(_do)

    # -- utility -----------------------------------------------------------
    def file_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0
