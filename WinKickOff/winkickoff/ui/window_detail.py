"""The right panel of the main window: description, unknown choices, Back and Forward, parameters.

Methods of MainWindow (ui/main_window.py); the attributes they use are made there."""

from __future__ import annotations

import json
import logging
import os
import tkinter as tk
from tkinter import ttk
from typing import Any

from winkickoff.core.catalog import (
    IMPORTED_PREFIX,
    Action,
    Catalog,
    Param,
    Rule,
    import_kind,
    import_rank,
    is_imported,
)
from winkickoff.core import admx as admx_module
from winkickoff.core import linked
from winkickoff.core.i18n import catalog_texts, language, tr
from winkickoff.core.profile import LEGACY_SOURCE
from winkickoff.core.render import RenderError, render_action, substitute
from winkickoff.core.validate import list_problem
from winkickoff.core.verify import rollback_steps, verify_steps
from winkickoff.ui.data_forms import AccountsForm, InstallForm, LanguagesForm
from winkickoff.ui.window_common import (
    WORKFLOW_NODE,
    HISTORY_LIMIT,
    GROUP_LIST_LIMIT,
    LEVEL_TITLES,
    PHASE_TITLES,
    UNKNOWN_NODE,
    UNKNOWN_PREFIX,
    UNKNOWN_TITLE,
    UNKNOWN_SUMMARY,
    UNKNOWN_POLICY,
    UNKNOWN_HELD,
    KIND_TITLES,
    UNKNOWN_RULE,
    VALUE_LIMIT,
    WORKFLOW,
    rule_of,
)

log = logging.getLogger(__name__)


class DetailPanel:
    """The right panel of the main window: description of the selected node, unknown choices, Back and Forward, parameters."""

    # ----------------------------------------------------------------- right panel

    def _show_panel(self, form_key: str | None) -> None:
        for key, form in self.forms.items():
            if key != form_key:
                form.pack_forget()
        if form_key is None:
            if not self.detail_view.winfo_ismapped():
                self.detail_view.pack(fill=tk.BOTH, expand=True)
            return
        self.detail_view.pack_forget()
        if form_key not in self.forms:
            factory = {"data:install": InstallForm, "data:accounts": AccountsForm, "data:languages": LanguagesForm}[form_key]
            self.forms[form_key] = factory(self.right, self)
        form = self.forms[form_key]
        form.refresh()
        form.pack(fill=tk.BOTH, expand=True)

    def show_item(self, item: str) -> None:
        self._current_item = item
        if item.startswith("data:"):
            self._show_panel(item)
            return
        self._show_panel(None)
        if item.startswith("r:"):
            rule = self.catalog.rules[rule_of(item)]
            self._write_detail(self._rule_parts(rule))
            self._build_params(rule)
        elif item.startswith("g:"):
            self._write_detail(self._group_parts(item[2:]))
            self._build_group_buttons(item[2:])
        elif item == UNKNOWN_NODE or item.startswith(UNKNOWN_PREFIX):
            self._show_unknown(item)
        else:
            self._write_detail([(tag, tr(text)) for tag, text in WORKFLOW])
            self._clear_params()

    def _rule_parts(self, rule: Rule) -> list[tuple[str, str]]:
        params = self.profile.params_for(self.catalog, rule.id)
        enabled = self.profile.is_enabled(rule.id)
        parts: list[tuple[str, str]] = [
            ("h1", self.rule_title(rule.id)),
            ("muted", tr("{0}   |   level: {1}   |   {2}   |   {3}", tr("Enabled") if self._rule_on(rule) else tr("Disabled"),
                         tr(LEVEL_TITLES.get(rule.level, rule.level)), tr(PHASE_TITLES.get(rule.phase, rule.phase)), rule.id)),
            ("", self.rule_text(rule, "summary")),
        ]
        found = linked.link(self.catalog, self.profile, rule.id)
        if found is not None and rule.id in self._covered and not enabled:
            params = dict(found.params)  # the values the built-in rule writes, not the unused ones of the policy
        if found is not None and self.profile.is_enabled(found.rule):
            parts.append(("changed", tr("Set by the built-in rule \"{0}\", which is on: this check mark follows it, and the "
                                        "policy is not written separately.", self.rule_title(found.rule))))
        elif found is not None and found.equal:
            parts.append(("changed", tr("The built-in rule \"{0}\" sets the same: checking this policy switches that rule on.",
                                        self.rule_title(found.rule))))
        origin = self.catalog.origins.get(rule.id)
        same = self.catalog.same_values(rule.id) if self.catalog.origins else []
        if same:
            parts.append(("h2", tr("Built into the catalog") if origin else tr("Also in imported templates")))
            parts.append(("muted", tr("These built-in rules set the same registry values; they are reviewed and documented, prefer them.")
                          if origin else tr("These imported policies set the same registry values as this rule.")))
            parts += [(f"link:r:{other}", "    " + self._rule_link_text(other)) for other in same]
        parts.append(("h2", tr("What it does technically")))
        parts += [("mono", self._action_text(action, params)) for action in rule.actions]
        effect = self.rule_text(rule, "effect")
        if effect:  # an imported policy may have no more than its summary
            parts += [("h2", tr("Effect")), ("", effect)]
        if rule.risk:
            parts += [("h2", tr("Risks and side effects")), ("risk", self.rule_text(rule, "risk"))]
        if rule.versions:
            parts += [("h2", tr("Windows versions")), ("", self.rule_text(rule, "versions"))]
        parts.append(("h2", tr("Dependencies")))
        for caption, ids, optional in (
            (tr("Requires"), list(rule.requires), False),
            (tr("Disabled along with it"), self.resolver.dependents(rule.id), False),
            (tr("Conflicts with"), list(rule.conflicts), True),
        ):
            if not ids and optional:
                continue
            parts.append(("", f"{caption}: {tr("nothing")}" if not ids else f"{caption}:"))
            parts += [(f"link:r:{other}", "    " + self._rule_link_text(other)) for other in ids]
        parts.append(("h2", tr("Check after installation")))
        if rule.verify:
            parts.append(("mono", self.rule_text(rule, "verify")))
        else:
            parts.append(("muted", tr("Generated from the rule's actions:")))
            parts += [("mono", step) for step in verify_steps(rule, params)]
        parts.append(("h2", tr("Rollback")))
        if rule.rollback:
            parts.append(("", self.rule_text(rule, "rollback")))
        else:
            parts.append(("muted", tr("Generated from the rule's actions:")))
            parts += [("mono", step) for step in rollback_steps(rule, params)]
        if origin is not None:
            parts += [("h2", tr("Source")), ("", tr("Policy {0} of the template {1}", origin.policy, origin.file)),
                      ("muted", tr("Imported templates \"{0}\" from {1}", origin.import_name, origin.folder))]
            trees = list(dict.fromkeys(self.group_title(".".join(g.split(".")[:2])) for g in self.catalog.placements(rule.id)))
            if len(trees) > 1:
                parts.append(("muted", tr("Shown in the imported trees: {0}; one check mark for all of them", "; ".join(trees))))
        else:
            parts += [("h2", tr("More details")), (f"link:doc:{rule.doc}", tr("Reference entry: ") + rule.doc)]
        return parts

    def _rule_link_text(self, rule_id: str) -> str:
        state = tr("enabled") if self.profile.is_enabled(rule_id) else tr("disabled")
        return f"{self.rule_title(rule_id)} ({state})"

    def _group_parts(self, group_id: str) -> list[tuple[str, str]]:
        group = self.catalog.groups[group_id]
        on, total = self._group_counts(group_id)
        summary = catalog_texts().group(group, "summary")
        parts: list[tuple[str, str]] = [("h1", self.group_title(group_id)), ("muted", tr("Rules: {0}, enabled: {1}", total, on))]
        if summary:
            parts.append(("", summary))
        parts.append(("h2", tr("Rules in this group")))
        rules = self.catalog.rules_in_group(group_id)
        for rule in rules[:GROUP_LIST_LIMIT]:
            mark = "[x]" if self._rule_on(rule) else "[ ]"
            parts.append((f"link:r:{rule.id}", f"{mark} {self.rule_title(rule.id)}"))
        if len(rules) > GROUP_LIST_LIMIT:
            parts.append(("muted", tr("... and {0} more: open the branches or use the search", len(rules) - GROUP_LIST_LIMIT)))
        return parts

    # ----------------------------------------------------------------- unknown choices of the profile

    def _show_unknown(self, item: str) -> None:
        """The root of the unknown choices or one of them: what the profile keeps, and the saved imports that have
        the policies (showing one brings the choices back)."""
        entries = self.profile.unknown_entries()
        if item != UNKNOWN_NODE:
            entries = [entry for entry in entries if entry[0] == item[len(UNKNOWN_PREFIX):]]
        if not entries:  # the profile changed under the item
            self._write_detail([(tag, tr(text)) for tag, text in WORKFLOW])
            self._clear_params()
            return
        sources, missing, held, widest = self._unknown_sources([entry[0] for entry in entries])
        single = item != UNKNOWN_NODE
        parts = self._unknown_entry_parts(entries[0]) if single else self._unknown_root_parts(entries)
        if sources or missing or held:
            parts.append(("h2", tr("Imported templates")))
            for info, count in sources:
                parts.append(("", tr("The saved imported templates \"{0}\" have this policy; they are hidden now.", info.name) if single
                              else tr("The saved imported templates \"{0}\" have {1} of these policies; they are hidden now.", info.name, count)))
            if missing:
                parts.append(("", tr("None of the imported templates saved in the program folder has this policy: import the "
                                     "templates that define it.") if single else
                              tr("{0} of these policies are in none of the imported templates saved in the program folder: "
                                 "import the templates that define them.", missing)))
            if held:  # the shown templates have the policy, but they are less trusted than the source of the choice
                parts.append(("", tr("No hidden saved import of the source of the choice or a more trusted one has this "
                                     "policy: import such templates, or choose the policy again in its branch.") if single else
                              tr("{0} of these choices wait for templates of their source or a more trusted one, and no hidden "
                                 "saved import has them: import such templates, or choose the policies again in their "
                                 "branches.", held)))
        self._write_detail(parts)
        self._build_unknown_buttons(item, sources, missing + held, widest)

    def _kept_source(self, rule_id: str) -> str:
        """The kind of import a kept choice of an imported policy was made in: its saved "source", or LEGACY_SOURCE for
        a choice saved before 1.3 or of a kind this version does not know (as core/profile.py counts it)."""
        entry = self.profile.unknown.get(rule_id)
        source = entry.get("source") if isinstance(entry, dict) else None
        return source if source in KIND_TITLES else LEGACY_SOURCE

    def _held_source(self, rule_id: str) -> str | None:
        """The kind a held choice was made in (core/profile.py: the policy is loaded, but from a less trusted
        import), or None for a choice of a rule that is not loaded."""
        return self._kept_source(rule_id) if rule_id in self.catalog.rules else None

    def _unknown_entry_parts(self, entry: tuple[str, bool, dict[str, Any]]) -> list[tuple[str, str]]:
        rule_id, enabled, params = entry
        held = self._held_source(rule_id)
        origin = self.catalog.origins.get(rule_id)
        if held is not None and origin is not None:
            status = tr("{0}   |   held: a less trusted source holds the policy now", tr("Enabled") if enabled else tr("Disabled"))
            text = tr(UNKNOWN_HELD, tr(KIND_TITLES[held]), tr(KIND_TITLES.get(origin.kind, KIND_TITLES["package"])))
        else:
            status = tr("{0}   |   not in the loaded catalog", tr("Enabled") if enabled else tr("Disabled"))
            text = tr(UNKNOWN_POLICY) if is_imported(rule_id) else tr(UNKNOWN_RULE, self.catalog.version)
        parts: list[tuple[str, str]] = [
            ("h1", rule_id),
            ("muted", status),
            ("", text),
            ("h2", tr("Kept in the profile")),
            ("", tr("State: {0}", tr("enabled") if enabled else tr("disabled"))),
        ]
        if not params:
            return parts + [("muted", tr("No parameters"))]
        return parts + [("", tr("Parameters:"))] + [("mono", f"{name} = {self._kept_value(value)}") for name, value in params.items()]

    def _unknown_root_parts(self, entries: list[tuple[str, bool, dict[str, Any]]]) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = [
            ("h1", tr(UNKNOWN_TITLE)),
            ("muted", tr("Rules: {0}, enabled: {1}", len(entries), sum(1 for entry in entries if entry[1]))),
            ("", tr(UNKNOWN_SUMMARY)),
            ("h2", tr("Kept in the profile")),
        ]
        for rule_id, enabled, _params in entries[:GROUP_LIST_LIMIT]:
            parts.append((f"link:{UNKNOWN_PREFIX}{rule_id}", f"{'[x]' if enabled else '[ ]'} {rule_id}"))
        if len(entries) > GROUP_LIST_LIMIT:
            parts.append(("muted", tr("... and {0} more: open the branches or use the search", len(entries) - GROUP_LIST_LIMIT)))
        return parts

    @staticmethod
    def _kept_value(value: Any) -> str:
        """A parameter value as the profile file holds it, cut when it is long."""
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= VALUE_LIMIT else text[:VALUE_LIMIT] + "..."

    def _hidden_imports_with(self, rule_id: str) -> list[admx_module.ImportInfo]:
        """Saved imports, hidden now, that have this policy. Their policies are read once per window: every change of
        the imports rebuilds the window."""
        if self._saved_imports is None:
            self._saved_imports = admx_module.list_imports(self.paths.admx)
        found = []
        for info in self._saved_imports:
            if info.id in self.settings.admx:
                continue
            ids = self._import_ids.get(info.id)
            if ids is None:
                try:
                    ids = admx_module.policy_ids(admx_module.load_import(self.paths.admx, info.id)[1], language())
                except (admx_module.AdmxError, AttributeError, KeyError, TypeError) as exc:
                    log.warning("import %s not read: %s", info.id, exc)
                    ids = set()
                self._import_ids[info.id] = ids
            if admx_module.has_policy(ids, rule_id):
                found.append(info)
        # only an import of the kind of the choice or a more trusted one brings it back: from a less trusted one it
        # would be held (core/profile.py), whether the policy is loaded now or not
        kept = import_rank(self._kept_source(rule_id))
        return [info for info in found if import_rank(import_kind(info.id)) <= kept]

    def _unknown_sources(self, rule_ids: list[str]) -> tuple[list[tuple[admx_module.ImportInfo, int]], int, int, int]:
        """The hidden saved imports that bring some of these choices back, with how many; how many choices of policies
        that are not loaded none of them has; how many held choices (the policy is loaded from a less trusted import)
        none of them has; and the rank of the least trusted kind of import that still brings one of those two back
        (-1 when there are none), which decides the import commands offered."""
        hits: dict[str, tuple[admx_module.ImportInfo, int]] = {}
        missing = held = 0
        widest = -1
        for rule_id in rule_ids:
            if not is_imported(rule_id):
                continue
            found = self._hidden_imports_with(rule_id)
            if not found:
                if rule_id in self.catalog.rules:
                    held += 1
                else:
                    missing += 1
                widest = max(widest, import_rank(self._kept_source(rule_id)))
            for info in found:
                hits[info.id] = (info, hits[info.id][1] + 1 if info.id in hits else 1)
        return list(hits.values()), missing, held, widest

    def _build_unknown_buttons(self, item: str, sources: list[tuple[admx_module.ImportInfo, int]], missing: int,
                               widest: int) -> None:
        """Show a hidden import that has the policies (the window opens on the policy or on the tree), or import new
        templates of a kind that brings the choices back (widest: see _unknown_sources)."""
        self._clear_params()
        buttons = []
        for info, _count in sources:
            target = "g:" + IMPORTED_PREFIX + info.id if item == UNKNOWN_NODE else "r:" + item[len(UNKNOWN_PREFIX):]
            buttons.append((tr("Show \"{0}\"", info.name), lambda i=info.id, t=target: self.show_templates(i, True, t)))
        if missing:
            commands = (("system", tr("Import the templates of this Windows"), lambda: self.import_templates(True)),
                        ("folder", tr("Import templates from a folder..."), lambda: self.import_templates(False)),
                        ("package", tr("Import a catalog file..."), lambda: self.import_catalog_file()))
            buttons += [(text, command) for kind, text, command in commands if import_rank(kind) <= widest]
        if not buttons:
            return
        self.params_frame.configure(text=tr("Imported templates"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for text, command in buttons:
            ttk.Button(self.params_frame, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

    def _action_text(self, action: Action, params: dict[str, Any]) -> str:
        f = action.fields
        if action.type == "xml-oobe":
            value = substitute(f["value"], params)
            return tr("XML, initial setup: <{0}>{1}</{2}>", f['element'], value, f['element'])
        if action.type in ("xml-pe-command", "xml-specialize-command"):
            return tr("XML, command: {0}", f['command'])
        try:
            return render_action(action, params)
        except (RenderError, KeyError) as exc:
            return f"{action.type}: {exc}"

    def _write_detail(self, parts: list[tuple[str, str]]) -> None:
        """Parts are (tag, line). A tag "link:<target>" makes the line clickable: the target is a tree
        node ("r:<rule>", "g:<group>") or "doc:<path#anchor>" (a card of the reference)."""
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        for name in self._link_tags:
            self.detail.tag_delete(name)
        self._link_tags = []
        for tag, text in parts:
            if tag.startswith("link:"):
                name = f"link{len(self._link_tags)}"
                self._link_tags.append(name)
                self.detail.insert(tk.END, text, ("link", name))
                self.detail.insert(tk.END, "\n")
                self.detail.tag_bind(name, "<Button-1>", lambda _e, target=tag[5:]: self.follow_link(target))
            else:
                self.detail.insert(tk.END, text + "\n", tag or ())
        self.detail.configure(state=tk.DISABLED)
        self.detail.yview_moveto(0)

    def follow_link(self, target: str) -> None:
        if target.startswith("doc:"):
            self.open_doc(target[4:])
        else:
            self._remember(target)
            self.select_node(target)

    # ----------------------------------------------------------------- Back and Forward

    def _remember(self, target: str) -> None:
        """Keep the node shown now for Back before another one is shown (a link, a message, a click in the tree)."""
        current = self._current_item
        if not current or target == current:
            return
        if not self._history or self._history[-1] != current:
            self._history.append(current)
            del self._history[:-HISTORY_LIMIT]
        self._future.clear()
        self._update_nav()

    def can_show(self, item: str) -> bool:
        if item == WORKFLOW_NODE or item.startswith("data:"):
            return True
        if item == UNKNOWN_NODE:
            return bool(self.profile.unknown)
        if item.startswith(UNKNOWN_PREFIX):
            return item[len(UNKNOWN_PREFIX):] in self.profile.unknown
        if item.startswith("g:"):
            return item[2:] in self.catalog.groups
        return item.startswith("r:") and rule_of(item) in self.catalog.rules

    def _step(self, source: list[str], target: list[str]) -> None:
        while source:
            item = source.pop()
            if self.can_show(item) and item != self._current_item:
                target.append(self._current_item)
                self.select_node(item)
                break
        self._update_nav()

    def go_back(self) -> None:
        self._step(self._history, self._future)

    def go_forward(self) -> None:
        self._step(self._future, self._history)

    def _update_nav(self) -> None:
        self.back_button.state(["!disabled"] if self._history else ["disabled"])
        self.forward_button.state(["!disabled"] if self._future else ["disabled"])

    def open_doc(self, doc: str) -> None:
        """Open a card of the reference in the program Windows associates with .md files."""
        path = self.paths.docs_root / doc.split("#", 1)[0]
        if not path.exists():
            self.set_status(tr("Reference entry not found: {0}", path))
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            self.set_status(tr("Opened reference entry: {0}", path.name) + (tr(", section \"{0}\"", doc.split('#', 1)[1]) if "#" in doc else ""))
        except OSError as exc:
            self.set_status(tr("Could not open the reference entry: {0}", exc))

    def _clear_params(self) -> None:
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self._param_vars = []
        self._param_marks = {}
        self._param_boxes = {}
        self.params_frame.pack_forget()

    def _build_group_buttons(self, group_id: str) -> None:
        self._clear_params()
        self.params_frame.configure(text=tr("Whole group"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        buttons = [
            (tr("Enable all"), lambda: self._group_action(group_id, True)),
            (tr("Disable all"), lambda: self._group_action(group_id, False)),
            (tr("Catalog defaults"), lambda: self._group_reset(group_id)),
        ]
        if is_imported(group_id):
            buttons = buttons[1:2]  # imported policies are switched on one by one
            if group_id.count(".") == 1:  # the root of an imported tree: "admx.<import id>"
                import_id = group_id[len(IMPORTED_PREFIX):]
                buttons.append((tr("Rename..."), lambda: self.rename_templates(import_id, self.group_title(group_id))))
        for text, command in buttons:
            ttk.Button(self.params_frame, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

    def _group_action(self, group_id: str, enabled: bool) -> None:
        scope = {r.id for r in self.catalog.rules_in_group(group_id)}
        self._apply_changes(self.resolver.set_group(self.profile, group_id, enabled), scope)
        self.show_item("g:" + group_id)

    def _group_reset(self, group_id: str) -> None:
        scope = {r.id for r in self.catalog.rules_in_group(group_id)}
        self._apply_changes(self.resolver.reset_group(self.profile, group_id), scope)
        self.show_item("g:" + group_id)

    def _build_params(self, rule: Rule) -> None:
        self._clear_params()
        if not rule.params:
            return
        self.params_frame.configure(text=tr("Rule parameters"))
        if rule.id in self._covered and not self.profile.is_enabled(rule.id):
            self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
            ttk.Label(self.params_frame, style="Note.TLabel", text=tr(
                "The values come from the built-in rule while it is on; to set them separately, switch that rule off.")).pack(anchor=tk.W)
            return
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for row, param in enumerate(rule.params.values()):
            sticky = tk.NW if param.type == "list" else tk.W
            ttk.Label(self.params_frame, text=self.param_title(rule, param)).grid(row=row, column=0, sticky=sticky, padx=(0, 12), pady=2)
            self._param_widget(rule, param).grid(row=row, column=1, sticky=tk.W, pady=2)
            hint = tr("default: {0}", self._param_display(rule, param, param.default))
            if param.type == "int" and (param.min is not None or param.max is not None):
                hint += tr(", range {0}..{1}", param.min, param.max)
            if param.type == "list":
                hint = (tr("one item per line, as name=value") if param.pairs else tr("one item per line")) + "\n" + hint
            ttk.Label(self.params_frame, text=hint, style="Note.TLabel").grid(row=row, column=2, sticky=sticky, padx=(10, 0))
            mark = ttk.Label(self.params_frame, style="Changed.TLabel")
            mark.grid(row=row, column=3, sticky=tk.W, padx=(10, 0))
            self._param_marks[param.name] = mark
            self._update_param_mark(rule, param)
        ttk.Button(self.params_frame, text=tr("Restore defaults"), command=lambda: self._reset_params(rule)).grid(
            row=len(rule.params), column=1, sticky=tk.W, pady=(6, 0)
        )

    def _param_display(self, rule: Rule, param: Param, value: Any) -> str:
        if param.type == "enum":
            return next((title for v, title in self.param_options(rule, param) if v == value), str(value))
        if param.type == "bool":
            return tr("yes") if value else tr("no")
        if param.type == "list":
            return "; ".join(str(item) for item in value) if isinstance(value, list) and value else tr("empty list")
        return str(value)

    def _list_widget(self, rule: Rule, param: Param, value: Any) -> tk.Widget:
        """A text box for a list parameter: one item per line; empty lines and spaces around items are dropped."""
        frame = ttk.Frame(self.params_frame)
        items = [str(item) for item in value] if isinstance(value, list) else []
        box = tk.Text(frame, width=46, height=min(max(len(items) + 1, 4), 10), wrap=tk.NONE, font=self.font_mono, undo=True)
        self._style_text(box)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        box.pack(side=tk.LEFT, fill=tk.BOTH)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        box.insert("1.0", "\n".join(items))
        box.edit_modified(False)

        def changed(_event: object = None) -> None:
            if not box.edit_modified():
                return  # the flag was just reset below
            box.edit_modified(False)
            lines = [line.strip() for line in box.get("1.0", "end-1c").splitlines()]
            self._set_param(rule, param, [line for line in lines if line])
            problem = list_problem(self.profile.param(self.catalog, rule.id, param.name), param.pairs)
            if problem:
                self.set_status(f"\"{self.param_title(rule, param)}\": {problem}")

        box.bind("<<Modified>>", changed)
        box.bind("<Tab>", lambda _e: (box.tk_focusNext().focus_set(), "break")[1])  # Tab leaves the box, as in a form
        self._param_boxes[param.name] = box
        return frame

    def _param_widget(self, rule: Rule, param: Param) -> tk.Widget:
        value = self.profile.param(self.catalog, rule.id, param.name)
        if param.type == "list":
            return self._list_widget(rule, param, value)
        if param.type == "enum":
            options = self.param_options(rule, param)
            var = tk.StringVar(value=self._param_display(rule, param, value))
            box = ttk.Combobox(self.params_frame, textvariable=var, values=[t for _, t in options], state="readonly", width=46)
            box.bind("<<ComboboxSelected>>", lambda _e: self._set_param(rule, param, next(v for v, t in options if t == var.get())))
            widget: tk.Widget = box
        elif param.type == "bool":
            var = tk.BooleanVar(value=bool(value))
            widget = ttk.Checkbutton(self.params_frame, variable=var, command=lambda: self._set_param(rule, param, bool(var.get())))
        elif param.type == "int":
            var = tk.StringVar(value=str(value))
            widget = ttk.Spinbox(self.params_frame, textvariable=var, from_=param.min if param.min is not None else 0,
                                 to=param.max if param.max is not None else 10**9, width=12)
            var.trace_add("write", lambda *_: self._set_param_text(rule, param, var.get()))
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(self.params_frame, textvariable=var, width=24)
            var.trace_add("write", lambda *_: self._set_param(rule, param, var.get().strip()))
        self._param_vars.append(var)
        return widget

    def _update_param_mark(self, rule: Rule, param: Param) -> None:
        """A parameter that differs from the catalog default is marked next to its hint."""
        mark = self._param_marks.get(param.name)
        if mark is not None:
            mark.configure(text=tr("changed") if param.name in self.profile.rules[rule.id].params else "")

    def _set_param_text(self, rule: Rule, param: Param, raw: str) -> None:
        try:
            value = int(raw)
        except ValueError:
            self.set_status(tr("\"{0}\": an integer is required", self.param_title(rule, param)))
            return
        if param.min is not None and value < param.min or param.max is not None and value > param.max:
            self.set_status(tr("\"{0}\": allowed range is {1} to {2}", self.param_title(rule, param), param.min, param.max))
            return
        self._set_param(rule, param, value)

    def _set_param(self, rule: Rule, param: Param, value: Any) -> None:
        state = self.profile.rules[rule.id]
        current = self.profile.param(self.catalog, rule.id, param.name)
        if value == current:
            return
        if value == param.default:
            state.params.pop(param.name, None)
        else:
            state.params[param.name] = value
        self.mark_dirty()
        self.set_status(f"{self.rule_title(rule.id)}: {self.param_title(rule, param)} = {self._param_display(rule, param, value)}")
        self._update_param_mark(rule, param)
        self.refresh_marks()
        self._write_detail(self._rule_parts(rule))

    def _reset_params(self, rule: Rule) -> None:
        if self.profile.rules[rule.id].params:
            self.profile.rules[rule.id].params.clear()
            self.mark_dirty()
            self.refresh_marks()
        self.show_item("r:" + rule.id)
