"""The resources of the MCP server: the same JSON as the read tools, and the documentation shipped with the program.

URIs use the scheme winkickoff:. Documentation files are resolved against an allow list taken at start, never from
request text to a path; the appendices, the technical editor documentation, AGENTS.md, settings and logs are not
addressable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from winkickoff.core.i18n import language
from winkickoff.mcp import MAX_DOC_BYTES
from winkickoff.mcp.jsonrpc import RESOURCE_NOT_FOUND, JsonRpcError
from winkickoff.mcp.redact import TITLE, clean_text
from winkickoff.mcp.tools import ToolContext, ToolError, group_rows, messages_payload, profile_payload, rule_card, status_payload

SCHEME = "winkickoff://"
JSON = "application/json"
MARKDOWN = "text/markdown"
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,60}\.md$")
LANG_RE = re.compile(r"^[a-z]{2,3}$")


class ResourceRegistry:
    def __init__(self, paths: Any, languages: tuple[str, ...]) -> None:
        self.paths = paths
        self.languages = languages
        self.reference = self._listing(Path(paths.docs_root) / "docs" / "technical" / "reference")
        self.user: dict[str, list[str]] = {}
        for code in languages:
            files = self._listing(Path(paths.docs_root) / "docs" / "user" / code)
            if files:
                self.user[code] = files

    @staticmethod
    def _listing(folder: Path) -> list[str]:
        try:
            return sorted(p.name for p in folder.iterdir() if p.is_file() and FILE_RE.match(p.name))
        except OSError:
            return []

    def listing(self) -> list[dict[str, Any]]:
        fixed = [
            {"uri": SCHEME + "status", "name": "status", "title": "Server and profile status", "mimeType": JSON},
            {"uri": SCHEME + "profile", "name": "profile", "title": "The open profile (redacted)", "mimeType": JSON},
            {"uri": SCHEME + "catalog/groups", "name": "groups", "title": "The group tree", "mimeType": JSON},
            {"uri": SCHEME + "catalog/rules", "name": "rules", "title": "Ids, titles and state of the built-in rules", "mimeType": JSON},
            {"uri": SCHEME + "messages", "name": "messages", "title": "The messages panel", "mimeType": JSON},
        ]
        docs = [{"uri": f"{SCHEME}docs/reference/{name}", "name": f"reference/{name}", "title": name, "mimeType": MARKDOWN}
                for name in self.reference]
        docs += [{"uri": f"{SCHEME}docs/user/{code}/{name}", "name": f"user/{code}/{name}", "title": name, "mimeType": MARKDOWN}
                 for code, names in self.user.items() for name in names]
        return fixed + docs

    def templates(self) -> list[dict[str, Any]]:
        return [
            {"uriTemplate": SCHEME + "catalog/rules/{id}", "name": "rule", "title": "One rule, as get_rule", "mimeType": JSON},
            {"uriTemplate": SCHEME + "docs/reference/{file}", "name": "reference", "title": "A card of the parameter reference",
             "mimeType": MARKDOWN},
            {"uriTemplate": SCHEME + "docs/user/{lang}/{file}", "name": "user-docs", "title": "A page of the user documentation",
             "mimeType": MARKDOWN},
        ]

    def read(self, uri: str, ctx: ToolContext) -> dict[str, Any]:
        """The resources/read result; JsonRpcError -32002 for anything not addressable."""
        if not isinstance(uri, str) or not uri.startswith(SCHEME):
            raise JsonRpcError(RESOURCE_NOT_FOUND, "resource not found", {"uri": uri})
        parts = uri[len(SCHEME):].split("/")
        try:
            if parts == ["status"]:
                return self._json(uri, status_payload(ctx))
            if parts == ["profile"]:
                return self._json(uri, profile_payload(ctx))
            if parts == ["messages"]:
                return self._json(uri, messages_payload(ctx))
            if parts == ["catalog", "groups"]:
                return self._json(uri, self._all_groups(ctx))
            if parts == ["catalog", "rules"]:
                return self._json(uri, self._builtin_rules(ctx))
            if len(parts) == 3 and parts[:2] == ["catalog", "rules"]:
                snap = ctx.snapshot()
                rule = snap.catalog.rules.get(parts[2])
                if rule is None:
                    raise JsonRpcError(RESOURCE_NOT_FOUND, "resource not found", {"uri": uri})
                return self._json(uri, rule_card(snap, ctx.texts(language()), rule, language()))
            if len(parts) == 3 and parts[:2] == ["docs", "reference"] and parts[2] in self.reference:
                return self._doc(uri, Path(self.paths.docs_root) / "docs" / "technical" / "reference" / parts[2])
            if len(parts) == 4 and parts[:2] == ["docs", "user"] and parts[3] in self.user.get(parts[2], []):
                return self._doc(uri, Path(self.paths.docs_root) / "docs" / "user" / parts[2] / parts[3])
        except ToolError as exc:
            raise JsonRpcError(RESOURCE_NOT_FOUND, exc.message, {"uri": uri, "error": exc.kind}) from exc
        raise JsonRpcError(RESOURCE_NOT_FOUND, "resource not found", {"uri": uri})

    def _all_groups(self, ctx: ToolContext) -> dict[str, Any]:
        snap = ctx.snapshot()  # one snapshot for the whole tree: one profile copy, consistent counts
        return {"groups": group_rows(snap, ctx.texts(language()), None, language(), deep=True)}

    def _builtin_rules(self, ctx: ToolContext) -> dict[str, Any]:
        snap = ctx.snapshot()
        texts = ctx.texts(language())
        rows = [{"id": r.id, "title": clean_text(texts.rule(r, "title"), TITLE), "enabled": snap.profile.is_enabled(r.id),
                 "level": r.level} for r in snap.catalog.rules.values() if r.id not in snap.catalog.origins]
        imports = [{"id": g.id[len("admx."):], "name": clean_text(g.title, TITLE), "policies": len(snap.catalog.rules_in_group(g.id))}
                   for g in snap.catalog.children(None) if g.id in snap.catalog.groups and g.id.startswith("admx.")]
        return {"rules": rows, "imports": imports, "note": "imported policies are listed by list_rules with group or query"}

    def _json(self, uri: str, payload: dict[str, Any]) -> dict[str, Any]:
        import json

        return {"contents": [{"uri": uri, "mimeType": JSON, "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}

    def _doc(self, uri: str, path: Path) -> dict[str, Any]:
        base = Path(self.paths.docs_root).resolve() / "docs"
        resolved = path.resolve()
        if not resolved.is_relative_to(base) or not resolved.is_file():
            raise JsonRpcError(RESOURCE_NOT_FOUND, "resource not found", {"uri": uri})
        text = resolved.read_bytes()[:MAX_DOC_BYTES].decode("utf-8", "ignore")
        return {"contents": [{"uri": uri, "mimeType": MARKDOWN, "text": clean_text(text, MAX_DOC_BYTES)}]}
