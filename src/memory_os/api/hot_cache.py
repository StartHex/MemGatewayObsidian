"""Hot Cache Manager — generates and maintains _meta/hot.md for session context injection.

hot.md is the bridge between sessions. It provides a concise summary of the
vault's current state so that each new Claude Code session starts with context.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from memory_os.vault.file_io import atomic_write, list_directory, safe_read
from memory_os.vault.frontmatter import parse_memory
from memory_os.vault.models import MemoryStatus

logger = structlog.get_logger(__name__)

_HOT_PATH = "_meta/hot.md"

# Fields that must be present in a valid memory file's frontmatter
_REQUIRED_FIELDS = {"id", "type", "status", "importance"}


class HotCacheManager:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path

    async def get(self) -> str | None:
        """Return current hot.md content, or None if it doesn't exist."""
        path = self.vault_path / _HOT_PATH
        if not path.exists():
            return None
        return await safe_read(path)

    async def generate(self, session_count: int = 0) -> str:
        """Generate hot.md content from current vault state."""
        vault = self.vault_path

        # 1. Active memories (top by strength, limited to 10)
        active_memories = await self._get_active_memories(limit=10)

        # 2. Recent activity (last 7 days from episodic/)
        recent_activity = await self._get_recent_activity(days=7)

        # 3. Pending items
        pending = await self._get_pending()

        # 4. Top decisions (importance > 70, limited to 8)
        top_decisions = await self._get_top_decisions(limit=8)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        vault_name = self.vault_path.name

        lines = [
            "# Hot Context",
            f"> Updated: {now} | Session #{session_count} | Vault: ~/{vault_name}",
            "",
        ]

        # Active Memories
        lines.append(f"## Active Memories ({len(active_memories)})")
        if active_memories:
            for m in active_memories:
                ago = self._format_ago(m.get("last_retrieved"))
                ago_str = f", last_retrieved: {ago}" if ago else ""
                lines.append(
                    f"- [[{m['id']}|{m.get('title', m['id'])}]] "
                    f"(strength: {m.get('strength', 0):.0f}{ago_str})"
                )
        else:
            lines.append("- No active memories yet")
        lines.append("")

        # Recent Activity
        lines.append(f"## Recent Activity ({len(recent_activity)} days)")
        if recent_activity:
            for day_entry in recent_activity:
                lines.append(f"- {day_entry}")
        else:
            lines.append("- No recent activity")
        lines.append("")

        # Pending
        total_pending = sum(pending.values())
        lines.append(f"## Pending ({total_pending})")
        if pending.get("inbox", 0) > 0:
            lines.append(f"- {pending['inbox']} inbox items waiting for consolidation")
        if pending.get("conflicts", 0) > 0:
            lines.append(f"- {pending['conflicts']} conflicts unresolved")
        if pending.get("fading", 0) > 0:
            lines.append(f"- {pending['fading']} fading memories below threshold")
        if total_pending == 0:
            lines.append("- Nothing pending")
        lines.append("")

        # Top Decisions
        lines.append("## Top Decisions")
        if top_decisions:
            for d in top_decisions:
                lines.append(f"- {d}")
        else:
            lines.append("- No key decisions recorded yet")

        content = "\n".join(lines) + "\n"
        hot_path = vault / _HOT_PATH
        hot_path.parent.mkdir(parents=True, exist_ok=True)
        await atomic_write(hot_path, content)

        logger.info("hot_cache_updated", session_count=session_count,
                     active=len(active_memories), days=len(recent_activity),
                     pending=total_pending)
        return content

    async def _get_active_memories(self, limit: int = 10) -> list[dict]:
        """Get top active memories by strength."""
        memories = []
        for mem_dir in ["_memory/semantic", "_memory/episodic", "_memory/procedural"]:
            dir_path = self.vault_path / mem_dir
            if not dir_path.exists():
                continue
            for f in await list_directory(dir_path, "*.md"):
                try:
                    node = await parse_memory(f)
                    if node.status == MemoryStatus.ACTIVE:
                        memories.append({
                            "id": node.id,
                            "title": node.title or node.id,
                            "strength": node.strength,
                            "importance": node.importance,
                            "last_retrieved": node.last_retrieved,
                        })
                except Exception:
                    continue

        memories.sort(key=lambda m: m["strength"], reverse=True)
        return memories[:limit]

    async def _get_recent_activity(self, days: int = 7) -> list[str]:
        """Get daily activity summary from episodic files."""
        today = datetime.now(timezone.utc).date()
        activity = {}
        epi_dir = self.vault_path / "_memory" / "episodic"
        if not epi_dir.exists():
            return []

        for f in await list_directory(epi_dir, "*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date()
                age = (today - mtime).days
                if age <= days:
                    day_str = mtime.isoformat()
                    activity[day_str] = activity.get(day_str, 0) + 1
            except Exception:
                continue

        result = []
        for day_str in sorted(activity.keys(), reverse=True):
            count = activity[day_str]
            label = f"{count} episodic entr{'ies' if count > 1 else 'y'}"
            result.append(f"{day_str}: {label}")
        return result

    async def _get_pending(self) -> dict[str, int]:
        """Count pending items: inbox, conflicts, fading."""
        pending = {"inbox": 0, "conflicts": 0, "fading": 0}

        # Inbox items
        inbox_dir = self.vault_path / "_inbox"
        if inbox_dir.exists():
            pending["inbox"] = len(await list_directory(inbox_dir, "*.md"))

        # Unresolved conflicts
        conflicts_path = self.vault_path / "_meta" / "cognitive-conflicts.md"
        if conflicts_path.exists():
            content = await safe_read(conflicts_path)
            pending["conflicts"] = content.count("## Conflict") + content.count("# Conflict")

        # Fading memories below threshold
        for mem_dir in ["_memory/semantic", "_memory/episodic", "_memory/procedural"]:
            dir_path = self.vault_path / mem_dir
            if not dir_path.exists():
                continue
            for f in await list_directory(dir_path, "*.md"):
                try:
                    node = await parse_memory(f)
                    if node.status == MemoryStatus.FADING and node.strength < 30:
                        pending["fading"] += 1
                except Exception:
                    continue

        return pending

    async def _get_top_decisions(self, limit: int = 8) -> list[str]:
        """Get key decisions (importance > 70 or title contains 'decision')."""
        decisions = []
        for mem_dir in ["_memory/semantic", "_memory/procedural"]:
            dir_path = self.vault_path / mem_dir
            if not dir_path.exists():
                continue
            for f in await list_directory(dir_path, "*.md"):
                try:
                    node = await parse_memory(f)
                    if node.importance >= 70 and node.status in (MemoryStatus.ACTIVE, MemoryStatus.FADING):
                        title = node.title or node.id
                        date_str = ""
                        if node.last_review:
                            date_str = f" ({node.last_review.strftime('%Y-%m-%d')})"
                        else:
                            ts = f.stat().st_mtime
                            date_str = f" ({datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')})"
                        decisions.append((node.importance, f"{title}{date_str}"))
                except Exception:
                    continue

        decisions.sort(key=lambda d: d[0], reverse=True)
        return [d[1] for d in decisions[:limit]]

    @staticmethod
    def _format_ago(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        delta = datetime.now(timezone.utc) - dt
        if delta.days > 30:
            return f"{delta.days // 30}mo ago"
        if delta.days > 0:
            return f"{delta.days}d ago"
        if delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        if delta.seconds > 60:
            return f"{delta.seconds // 60}m ago"
        return "just now"


async def validate_md_file(vault_path: Path, file_path: str) -> dict:
    """Validate a markdown file in the vault.

    Checks:
      - File exists
      - Required frontmatter fields present
      - Wikilinks point to existing files
    """
    full_path = vault_path / file_path
    if not full_path.exists():
        return {"valid": False, "issues": ["file not found"], "fields_ok": False, "links_ok": True}

    issues = []
    fields_ok = True
    links_ok = True

    # Parse frontmatter
    import frontmatter as fm
    try:
        post = fm.load(str(full_path))
        meta = dict(post.metadata)
    except Exception as e:
        return {"valid": False, "issues": [f"parse error: {e}"], "fields_ok": False, "links_ok": False}

    # Check required fields
    missing_fields = _REQUIRED_FIELDS - set(meta.keys())
    if missing_fields:
        issues.append(f"missing fields: {', '.join(sorted(missing_fields))}")
        fields_ok = False

    # Check wikilinks
    wikilinks = []
    content = post.content
    import re
    for match in re.finditer(r"\[\[([^\]|#]+)(?:[^\]\]]*)?\]\]", content):
        wikilinks.append(match.group(1).strip())

    broken = []
    for link in wikilinks:
        # Check if referenced file exists
        target = link
        if not target.endswith(".md"):
            target += ".md"
        # Search in memory directories
        found = False
        for search_dir in ["_memory/semantic", "_memory/episodic", "_memory/procedural",
                           "_inbox", "_working", "_meta"]:
            candidate = vault_path / search_dir / target
            if candidate.exists():
                found = True
                break
            # Also try glob match (might have slug suffix)
            stem = target.replace(".md", "")
            dir_path = vault_path / search_dir
            if dir_path.exists():
                for f in dir_path.glob(f"{stem}*.md"):
                    found = True
                    break
            if found:
                break
        if not found:
            broken.append(link)

    if broken:
        issues.append(f"broken wikilinks: {', '.join(broken[:5])}")
        links_ok = False

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "fields_ok": fields_ok,
        "links_ok": links_ok,
    }
