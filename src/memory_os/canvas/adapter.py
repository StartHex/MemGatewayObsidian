from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel

from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory
from memory_os.vault.index import get_all_active_ids
from memory_os.vault.vector_client import VectorStore


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    strength: float
    importance: float


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class HeatmapCell(BaseModel):
    id: str
    name: str
    strength: float
    importance: float
    status: str
    next_review: str | None = None


class HeatmapData(BaseModel):
    cells: list[HeatmapCell]


class TimelineBucket(BaseModel):
    date: str
    count: int
    items: list[dict]


class TimelineData(BaseModel):
    buckets: list[TimelineBucket]


class ProjectionPoint(BaseModel):
    id: str
    x: float
    y: float
    type: str
    strength: float
    label: str
    cluster: int = -1


class ProjectionData(BaseModel):
    points: list[ProjectionPoint]


class CanvasDataAdapter:
    def __init__(self, vault_path):
        self.vault_path = vault_path
        self.vector = VectorStore(vault_path)

    async def graph_data(self, status_filter: list[str] | None = None) -> GraphData:
        status_filter = status_filter or ["active"]
        active_ids = await get_all_active_ids(self.vault_path / "_meta" / "index.md")
        nodes = []
        edges = []
        for mid in list(active_ids)[:500]:
            try:
                node = await parse_memory(self._resolve_memory_path(mid))
                if node.status.value not in status_filter:
                    continue
                nodes.append(GraphNode(
                    id=node.id, label=self._title(node),
                    type=node.type.value, strength=node.strength,
                    importance=node.importance,
                ))
                for link in node.links_to:
                    target = link.replace("[[", "").replace("]]", "").split("/")[-1].replace(".md", "")
                    if target:
                        clean = target.split("/")[-1]
                        parts = clean.split("-")
                        if len(parts) >= 4:
                            clean = "-".join(parts[:4])
                        if clean and clean != node.id:
                            edges.append(GraphEdge(source=node.id, target=clean))
            except Exception:
                continue
        return GraphData(nodes=nodes, edges=edges)

    async def heatmap_data(self) -> HeatmapData:
        active_ids = await get_all_active_ids(self.vault_path / "_meta" / "index.md")
        cells = []
        for mid in list(active_ids)[:500]:
            try:
                node = await parse_memory(self._resolve_memory_path(mid))
                next_rv = node.next_review.isoformat() if node.next_review else None
                cells.append(HeatmapCell(
                    id=node.id, name=self._title(node),
                    strength=node.strength, importance=node.importance,
                    status=node.status.value, next_review=next_rv,
                ))
            except Exception:
                continue
        return HeatmapData(cells=cells)

    async def timeline_data(self, start: date, end: date, granularity: str = "day") -> TimelineData:
        epi_dir = self.vault_path / "_memory" / "episodic"
        files = await list_directory(epi_dir, "*.md")
        buckets: dict[str, TimelineBucket] = {}
        for f in files:
            try:
                d = f.stem[:10]
                node = await parse_memory(f)
                if d not in buckets:
                    buckets[d] = TimelineBucket(date=d, count=0, items=[])
                buckets[d].count += 1
                mem_id = node.id if node.id else f.stem
                if not mem_id or len(mem_id) < 8:
                    mem_id = f.stem  # fallback to filename stem
                buckets[d].items.append({
                    "id": mem_id,
                    "title": self._title(node),
                    "tags": node.tags,
                    "emotional_tag": node.emotional_tag,
                })
            except Exception:
                continue
        sorted_buckets = sorted(buckets.values(), key=lambda b: b.date)
        return TimelineData(buckets=sorted_buckets)

    async def vector_projection(self, memory_type: str = "semantic") -> ProjectionData:
        try:
            from umap import UMAP
            import numpy as np

            rows = self.vector.db.open_table(f"memory_{memory_type}").to_arrow().to_pylist()
            if len(rows) < 2:
                return ProjectionData(points=[])

            vectors = np.array([r["vector"] for r in rows])
            reducer = UMAP(n_components=2, random_state=42)
            embedding_2d = reducer.fit_transform(vectors)

            points = []
            for i, r in enumerate(rows):
                points.append(ProjectionPoint(
                    id=r["memory_id"], x=float(embedding_2d[i][0]),
                    y=float(embedding_2d[i][1]), type=memory_type,
                    strength=r.get("strength", 50), label=r["memory_id"][:20],
                ))
            return ProjectionData(points=points)
        except ImportError:
            return ProjectionData(points=[])

    def _title(self, node) -> str:
        return node.content.split("\n")[0].replace("# ", "")[:80] if node.content else node.id

    def _resolve_memory_path(self, memory_id: str):
        for subdir in ["_inbox", "_working", "_memory/semantic", "_memory/episodic", "_memory/procedural", "_memory/archive"]:
            p = self.vault_path / subdir / f"{memory_id}.md"
            if p.exists():
                return p
        return self.vault_path / "_memory" / "semantic" / f"{memory_id}.md"
