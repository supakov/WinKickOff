"""Profiles of the main window: the profile list, the draft, comparison and diff profiles, import from an
answer file, check and build.

Methods of MainWindow (ui/main_window.py); the attributes they use are made there."""

from __future__ import annotations

import logging
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Catalog
from winkickoff.core.diffprofile import load_diff, make_diff, merge_diff, save_diff
from winkickoff.core.draft import draft_text, drop_draft, save_draft
from winkickoff.core.i18n import catalog_texts, language, tr
from winkickoff.core.importer import IMPORTED_NAME, ImportFailed, import_xml
from winkickoff.core.profile import Profile, one_line
from winkickoff.core.pscheck import PsCheckResult, check_scripts
from winkickoff.core.render import BuildResult, RenderError, write_answer_file
from winkickoff.core.settings import Settings
from winkickoff.mcp.errors import ToolError
from winkickoff.mcp.workspace import POWERSHELL_NOTE
from winkickoff.core.validate import Issue, has_errors, validate_catalog, validate_profile, validate_xml
from winkickoff.ui.data_forms import ACCOUNT_MODE_TITLES
from winkickoff.ui.window_common import WORKFLOW_NODE, DRAFT_INTERVAL_MS, BUSY_NOTE, _profile_name, error_text

log = logging.getLogger(__name__)


class ProfileActions:
    """Profiles, the draft, comparison and diff profiles, import from an answer file, check and build."""

    # ----------------------------------------------------------------- profiles

    def refresh_profile_choices(self) -> None:
        choices: list[tuple[str, Path]] = []
        for path in sorted((self.paths.data / "profiles").glob("preset-*.json")):
            choices.append((tr("Preset: {0}", tr(_profile_name(path))), path))
        for path in sorted(self.paths.profiles.glob("*.json")):
            if not path.name.startswith("preset-"):
                choices.append((path.stem, path))
        self._choices = choices
        labels = [label for label, _ in choices]
        current = self._current_label()
        if current not in labels:
            labels.append(current)
        self.profile_box.configure(values=labels)
        self.profile_var.set(current)

    def _current_label(self) -> str:
        if self.profile.path is not None:
            for label, path in self._choices:
                if path.resolve() == self.profile.path.resolve():
                    return label
            return self.profile.path.stem
        return tr("{0} (not saved)", tr(self.profile.name))

    def _is_preset(self, path: Path | None) -> bool:
        return path is not None and path.name.startswith("preset-")

    def _on_profile_selected(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        label = self.profile_var.get()
        path = next((p for text, p in self._choices if text == label), None)
        if path is None or (self.profile.path is not None and path.resolve() == self.profile.path.resolve()):
            return
        if not self.load_profile_file(path):
            self.profile_var.set(self._current_label())

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = self._dialog(messagebox.askyesnocancel, APP_NAME, tr("Profile \"{0}\" has been changed. Save changes?", tr(self.profile.name)), parent=self)
        if answer is None:
            return False
        if answer:
            return self.save_profile()
        self.discard_draft()  # the person dropped the changes
        return True

    # ----------------------------------------------------------------- the draft (core/draft.py)

    def start_draft_timer(self) -> None:
        self._draft_job = self.after(DRAFT_INTERVAL_MS, self._draft_tick)

    def _draft_tick(self) -> None:
        self.write_draft()
        self._draft_job = self.after(DRAFT_INTERVAL_MS, self._draft_tick)

    def write_draft(self) -> bool:
        """Write the unsaved changes to the draft when they changed since the last one; True when they are safe (also
        when there is nothing unsaved)."""
        if not self.dirty:
            return True
        text = draft_text(self.profile, self.catalog)
        if text == self._draft_text:
            return True
        try:
            save_draft(self.paths.root, self.profile, self.catalog)
        except OSError as exc:
            log.warning("draft not written: %s", exc)
            return False
        self._draft_text = text
        return True

    def discard_draft(self) -> None:
        drop_draft(self.paths.root)
        self._draft_text = None

    def set_profile(self, profile: Profile, *, dirty: bool, warnings: list[str] | None = None) -> None:
        self.profile = profile
        self.dirty = dirty
        if not dirty:
            self.discard_draft()  # another profile is open as saved: the draft of the previous one goes
        if self.search_var.get().strip():
            self.apply_search()
        else:
            self.rebuild_tree()
        for form in self.forms.values():
            form.refresh()
        self.refresh_profile_choices()
        self.update_title()
        current = self._current_item if self.tree.exists(self._current_item) else WORKFLOW_NODE
        self.select_node(current)
        self.show_issues([Issue("info", "profile", w) for w in (warnings or [])])

    def load_profile_file(self, path: Path, confirm: bool = True) -> bool:
        """Open a profile file; confirm=False skips the "Save changes?" question and the error box (the MCP bridge)."""
        if confirm and not self.confirm_discard():
            return False
        try:
            profile, warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            if confirm:
                self._dialog(messagebox.showerror, APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return False
        self.last_load_warnings = list(warnings)
        self.set_profile(profile, dirty=False, warnings=warnings)
        if not self._is_preset(path):
            self.remember_file(path)
        kind = tr("Preset") if self._is_preset(path) else tr("Profile")
        self.set_status(tr("{0} \"{1}\" opened", kind, profile.name) + (tr(" (changes are saved under a new name)") if self._is_preset(path) else ""))
        return True

    def remember_file(self, path: Path | None) -> None:
        if path is None:
            return
        self.settings.add_recent(path, self.paths.root)
        self.settings.save(self.paths.settings_file)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.delete(0, tk.END)
        if not self.settings.recent:
            self.recent_menu.add_command(label=tr("(empty)"), state=tk.DISABLED)
            return
        for index, item in enumerate(self.settings.recent, start=1):
            self.recent_menu.add_command(label=f"{index}. {item}", command=lambda i=item: self.open_recent(i))

    def open_recent(self, item: str) -> bool:
        path = Settings.resolve(item, self.paths.root)
        if not path.exists():
            self._dialog(messagebox.showerror, APP_NAME, tr("File not found and removed from the recent list:\n{0}", path), parent=self)
            self.settings.forget(path, self.paths.root)
            self.settings.save(self.paths.settings_file)
            self._rebuild_recent_menu()
            return False
        if path.suffix.lower() == ".xml":
            return self.confirm_discard() and self.import_file(path)
        return self.load_profile_file(path)

    def open_profile_dialog(self) -> None:
        name = self._dialog(filedialog.askopenfilename, parent=self, title=tr("Open profile"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("WinKickOff profile"), "*.json"), (tr("All files"), "*.*")])
        if name:
            self.load_profile_file(Path(name))

    def save_profile(self) -> bool:
        if self.profile.path is None or self._is_preset(self.profile.path):
            return self.save_profile_as()
        try:
            self.profile.save(self.profile.path, self.catalog)
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not save the profile:\n{0}", exc), parent=self)
            return False
        self.dirty = False
        self.discard_draft()
        self.update_title()
        self.remember_file(self.profile.path)
        self.set_status(tr("Profile saved: {0}", self.profile.path))
        return True

    def save_profile_as(self) -> bool:
        suggested = re.sub(r'[\\/:*?"<>|]', "_", self.profile.name) or "profile"
        if self._is_preset(self.profile.path):
            suggested += tr(" (mine)")
        name = self._dialog(filedialog.asksaveasfilename, parent=self, title=tr("Save profile as"), initialdir=str(self.paths.profiles),
                                            initialfile=f"{suggested}.json", defaultextension=".json",
                                            filetypes=[(tr("WinKickOff profile"), "*.json")])
        if not name:
            return False
        path = Path(name)
        if path.name.startswith("preset-"):
            self._dialog(messagebox.showerror, APP_NAME, tr("The names preset-*.json are reserved for presets. Choose a different name."), parent=self)
            return False
        try:
            self.save_profile_to(path)
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not save the profile:\n{0}", exc), parent=self)
            return False
        return True

    def save_profile_to(self, path: Path) -> None:
        """Save the open profile under a new name (the tail of Save as; the MCP files mode uses it too)."""
        previous = self.profile.name
        self.profile.name = path.stem
        try:
            self.profile.save(path, self.catalog)
        except OSError:
            self.profile.name = previous  # a failed save leaves the profile as it was
            raise
        self.dirty = False
        self.discard_draft()
        self.refresh_profile_choices()
        self.update_title()
        self.remember_file(path)
        self.set_status(tr("Profile saved: {0}", path))

    # ----------------------------------------------------------------- comparison

    def compare_with_file(self) -> None:
        name = self._dialog(filedialog.askopenfilename, parent=self, title=tr("Compare with profile"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("WinKickOff profile"), "*.json"), (tr("All files"), "*.*")])
        if name:
            self.show_comparison(Path(name))

    def comparison_rows(self, other: Profile) -> list[tuple[str, str, str, str, str]]:
        """(tree node, kind, item, value here, value there) for every difference from other."""

        def state(value: Any) -> str:
            return "" if value is None else tr("enabled") if value else tr("disabled")

        install_titles = {"edition": tr("Edition"), "product_key_mode": tr("Key mode"), "product_key": tr("Product key"),
                          "time_zone": tr("Time zone")}
        account_modes = dict(ACCOUNT_MODE_TITLES)
        language_titles = {"ui_language": tr("Display language"), "system_locale": tr("Language for non-Unicode programs"),
                           "user_locale": tr("Date and number format"), "input": tr("Input languages")}

        def text(value: Any) -> str:
            return ", ".join(str(v) for v in value) if isinstance(value, list) else "" if value is None else str(value)

        rows: list[tuple[str, str, str, str, str]] = []
        for d in self.profile.diff(other, self.catalog):
            if d.kind == "rule":
                title = self.rule_title(d.key) if d.key in self.catalog.rules else d.key
                rows.append(("r:" + d.key, tr("rule"), title, state(d.before), state(d.after)))
            elif d.kind == "param":
                rule_id, _, name = d.key.rpartition(".")
                rule = self.catalog.rules.get(rule_id)
                if rule is not None and name in rule.params:
                    param = rule.params[name]
                    rows.append(("r:" + rule_id, tr("parameter"), f"{self.rule_title(rule_id)}: {self.param_title(rule, param)}",
                                 self._param_display(rule, param, d.before), self._param_display(rule, param, d.after)))
                else:
                    rows.append(("", tr("parameter"), d.key, text(d.before), text(d.after)))
            elif d.kind == "install" and d.key == "account_mode":
                rows.append(("data:accounts", tr("accounts"), tr("Accounts"), tr(account_modes.get(d.before, str(d.before))),
                             tr(account_modes.get(d.after, str(d.after)))))
            elif d.kind == "install":
                rows.append(("data:install", tr("installation"), install_titles.get(d.key, d.key), text(d.before), text(d.after)))
            elif d.kind == "languages":
                rows.append(("data:languages", tr("languages"), language_titles.get(d.key, d.key), text(d.before), text(d.after)))
            else:
                rows.append(("data:accounts", tr("accounts"), tr("account list"), text(d.before), text(d.after)))
        return rows

    def show_comparison(self, path: Path) -> tk.Toplevel | None:
        try:
            other, _warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return None
        return self.open_comparison(other, tr(other.name))

    def show_changes(self) -> tk.Toplevel | None:
        """The changes of the open profile since it was last saved (or since the preset it came from)."""
        path = self.profile.path
        if path is None or not Path(path).is_file():
            self._dialog(messagebox.showinfo, APP_NAME, tr("The profile has not been saved yet, so there is nothing to compare "
                                                            "it with. Use \"Compare with profile...\" instead."), parent=self)
            return None
        try:
            saved, _warnings = Profile.load(Path(path), self.catalog)
        except (OSError, ValueError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return None
        return self.open_comparison(saved, tr("saved"))

    def open_comparison(self, other: Profile, other_title: str) -> tk.Toplevel:
        """The differences of the open profile from other as a tree (groups, rules, their parameters, the data forms) with
        the description of the selected rule; the differences can be saved as a diff profile or applied to this PC."""
        rows = self.comparison_rows(other)
        window = tk.Toplevel(self)
        window.title(tr("Comparison: \"{0}\" and \"{1}\"", tr(self.profile.name), other_title))
        window.geometry("1100x580")
        caption = (tr("Differences: {0}. Select a rule to read its description; double-click to go to it.", len(rows)) if rows
                   else tr("The profiles are identical."))
        ttk.Label(window, text=caption, padding=(10, 8)).pack(anchor=tk.W)
        buttons = ttk.Frame(window, padding=(10, 6))
        buttons.pack(side=tk.BOTTOM, fill=tk.X)
        panes = ttk.PanedWindow(window, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=10)
        left = ttk.Frame(panes)
        table = ttk.Treeview(left, columns=("mine", "theirs"), show="tree headings")
        table.heading("#0", text=tr("Location"))
        table.column("#0", width=430)
        for column, title in (("mine", tr(self.profile.name)), ("theirs", other_title)):
            table.heading(column, text=title)
            table.column(column, width=150, stretch=False)
        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        detail = tk.Text(panes, wrap=tk.WORD, width=46, relief=tk.FLAT, padx=8, pady=6, state=tk.DISABLED)
        panes.add(left, weight=3)
        panes.add(detail, weight=2)
        targets: dict[str, str] = {}
        parents: dict[str, str] = {}
        for index, (target, kind, item, mine, theirs) in enumerate(rows):
            rule_id = target[2:] if target.startswith("r:") else ""
            if rule_id in self.catalog.rules:
                group = self.catalog.groups.get(self.catalog.rules[rule_id].group)
                while group is not None and group.parent:
                    group = self.catalog.groups.get(group.parent)
                top = f"g{group.id}" if group is not None else "gother"
                if top not in parents:
                    parents[top] = table.insert("", tk.END, iid=top, text=self.group_title(group.id) if group else tr("Rules"),
                                                open=True)
                node = f"n{rule_id}"
                if not table.exists(node):
                    table.insert(top, tk.END, iid=node, text=self.rule_title(rule_id), open=True)
                    targets[node] = target
                if kind == tr("rule"):
                    table.item(node, values=(mine, theirs))
                    continue
                parent, label = node, item.split(": ", 1)[-1]
            else:  # the branch once: setdefault would call insert again for every difference of the forms
                if "gdata" not in parents:
                    parents["gdata"] = table.insert("", tk.END, iid="gdata", text=tr("Data forms"), open=True)
                parent, label = parents["gdata"], f"{kind}: {item}"
            iid = f"d{index}"
            targets[iid] = target
            table.insert(parent, tk.END, iid=iid, text=label, values=(mine, theirs))

        def describe(_event: tk.Event | None = None) -> None:  # type: ignore[type-arg]
            selection = table.selection()
            target = targets.get(selection[0], "") if selection else ""
            texts = catalog_texts()
            lines: list[str] = []
            if target.startswith("r:") and target[2:] in self.catalog.rules:
                rule = self.catalog.rules[target[2:]]
                lines = [self.rule_title(rule.id), rule.id, ""] + [texts.rule(rule, field) for field in ("summary", "effect", "risk")
                                                                    if texts.rule(rule, field)]
            detail.configure(state=tk.NORMAL)
            detail.delete("1.0", tk.END)
            detail.insert("1.0", "\n\n".join(line for line in lines if line is not None))
            detail.configure(state=tk.DISABLED)

        def go(_event: tk.Event) -> None:  # type: ignore[type-arg]
            selection = table.selection()
            if selection and targets.get(selection[0]):
                self.select_node(targets[selection[0]])

        table.bind("<<TreeviewSelect>>", describe)
        table.bind("<Double-Button-1>", go)
        changed_rules = list(dict.fromkeys(t for t in targets.values() if t.startswith("r:") and t[2:] in self.catalog.rules))
        ttk.Button(buttons, text=tr("Close"), command=window.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text=tr("Apply these changes to this PC..."),
                   command=lambda: self.apply_now(changed_rules), state=tk.NORMAL if changed_rules else tk.DISABLED).pack(side=tk.RIGHT, padx=6)
        ttk.Button(buttons, text=tr("Save the differences as a diff profile..."),
                   command=lambda: self.save_diff_file(other), state=tk.NORMAL if rows else tk.DISABLED).pack(side=tk.RIGHT)
        window.comparison_rows = rows  # type: ignore[attr-defined]
        window.comparison_tree = table  # type: ignore[attr-defined]
        window.comparison_detail = detail  # type: ignore[attr-defined]
        window.changed_rules = changed_rules  # type: ignore[attr-defined]
        return window

    def save_diff_file(self, other: Profile) -> Path | None:
        """Only the differences of the open profile from other, as a diff profile (core/diffprofile.py)."""
        diff = make_diff(self.profile, other, self.catalog)
        suggested = re.sub(r'[\\/:*?"<>|]', "_", tr(self.profile.name)) or "profile"
        name = self._dialog(filedialog.asksaveasfilename, parent=self, title=tr("Save the differences as a diff profile"),
                            initialdir=str(self.paths.profiles), initialfile=f"{suggested}.wkdiff", defaultextension=".wkdiff",
                            filetypes=[(tr("WinKickOff diff profile"), "*.wkdiff")])
        if not name:
            return None
        try:
            save_diff(Path(name), diff)
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not save the profile:\n{0}", exc), parent=self)
            return None
        self.set_status(tr("Differences saved: {0}", name))
        return Path(name)

    def merge_diff_dialog(self) -> None:
        name = self._dialog(filedialog.askopenfilename, parent=self, title=tr("Merge a diff profile"), initialdir=str(self.paths.profiles),
                            filetypes=[(tr("WinKickOff diff profile"), "*.wkdiff"), (tr("All files"), "*.*")])
        if name:
            self.merge_diff_file(Path(name))

    def merge_diff_file(self, path: Path) -> int:
        """Merge a diff profile into the open profile (unsaved); returns how many items changed."""
        try:
            diff = load_diff(path)
        except ValueError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return 0
        changed, warnings = merge_diff(self.profile, diff, self.catalog)
        summary = tr("Diff profile \"{0}\" merged: {1} changes", one_line(str(diff.get("name") or path.stem)), changed)
        self.set_profile(self.profile, dirty=self.dirty or changed > 0, warnings=[summary] + warnings)
        self.set_status(summary)
        return changed

    def import_from_xml(self) -> None:
        if not self.confirm_discard():
            return
        name = self._dialog(filedialog.askopenfilename, parent=self, title=tr("Open profile from autounattend.xml"),
                                          filetypes=[(tr("Answer file"), "*.xml"), (tr("All files"), "*.*")])
        if name:
            self.import_file(Path(name))

    def import_file(self, path: Path) -> bool:
        """A WinKickOff build gives back its embedded profile; any other answer file of the same
        family (the hand-written v0.2) is imported by its actions, with a list of what is uncertain."""
        try:
            text = path.read_text(encoding="utf-8")
            profile, warnings = import_xml(text, self.catalog, self.resources.keyboards)
        except (OSError, UnicodeDecodeError, ImportFailed) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not restore the profile:\n{0}", exc), parent=self)
            return False
        by_actions = profile.name == IMPORTED_NAME
        if by_actions:
            profile.name = tr("Import {0}", path.stem)
        self.set_profile(profile, dirty=True, warnings=warnings)
        self.remember_file(path)
        how = tr("from the file's actions (uncertain items in the list below)") if by_actions else tr("from the embedded profile")
        self.set_status(tr("Profile \"{0}\" restored {1}; save it to use it again", profile.name, how))
        return True

    # ----------------------------------------------------------------- check and build

    def run_checks(self, *, with_powershell: bool) -> tuple[BuildResult | None, list[Issue]]:
        issues = validate_profile(self.profile, self.catalog, self.resources.keyboards)
        if has_errors(issues):
            return None, issues
        try:
            result = self.renderer.build(self.profile, app_version=APP_VERSION)
        except (RenderError, KeyError, ValueError, TypeError) as exc:  # never a silent failure of Check or Build
            return None, issues + [Issue("error", "build", tr("Cannot build: {0}", error_text(exc, 500)))]
        issues += validate_xml(result.xml)
        if with_powershell and not has_errors(issues):
            issues += self._ps_issues(check_scripts(result.scripts, self.paths.logs / "tmp"))
        return result, issues

    @staticmethod
    def _ps_issues(ps: PsCheckResult) -> list[Issue]:
        if ps.skipped:
            return [Issue("info", "powershell", tr("PowerShell syntax check skipped: powershell.exe not found"))]
        if ps.failure:
            return [Issue("warning", "powershell", tr("PowerShell syntax check could not be run: {0}", ps.failure))]
        if ps.errors:
            return [Issue("error", "powershell", e) for e in ps.errors]
        return [Issue("info", "powershell", tr("Script syntax (Windows PowerShell 5.1): no errors"))]

    def check(self) -> list[Issue]:
        result, issues = self.run_checks(with_powershell=False)
        if result is not None:
            issues.append(Issue("info", "build", tr("The file can be built: {0} rules, scripts: {1}", len(result.rule_ids), ', '.join(result.scripts) or tr("no scripts"))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Check: {0} errors, {1} warnings", errors, warnings) + (tr("; ready to build (F9)") if not errors else ""))
        return issues

    def check_catalog(self) -> list[Issue]:
        """Re-read the rule files from disk and report defects (useful while editing the catalog JSON)."""
        catalog, issues = validate_catalog(self.paths.rules, self.paths.docs_root)
        if catalog is not None:
            issues.append(Issue("info", "catalog", tr("Catalog {0} is readable: {1} rules, {2} groups. Changes to catalog files take effect after the program is restarted.", catalog.version, len(catalog.rules), len(catalog.groups))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Catalog check: {0} errors, {1} warnings", errors, warnings))
        return issues

    def write_build(self, result: BuildResult, path: Path) -> None:
        write_answer_file(result, path)
        self._last_output = path

    def write_answer_file_to(self, path: Path) -> tuple[BuildResult, list[Issue]]:
        """Check without PowerShell and write the answer file (the MCP files mode); refused when there are errors."""
        result, issues = self.run_checks(with_powershell=False)
        if result is None or has_errors(issues):
            self.show_issues(issues)
            raise ToolError("validation_failed", "the profile has errors; run check_profile",
                            {"errors": [i.message for i in issues if i.level == "error"]})
        self.write_build(result, path)
        issues = issues + [Issue("info", "powershell", tr(POWERSHELL_NOTE))]
        self.show_issues(issues + [Issue("info", "build", tr("Saved: {0} ({1} rules)", path, len(result.rule_ids)))])
        self.set_status(tr("Built: {0}", path))
        return result, issues

    def set_busy(self, busy: bool, text: str = "", *, notify: bool = False) -> None:
        """While a background check runs, Check and Build are unavailable (buttons and F7, F9). notify: a long operation
        (an import, the read of this PC) also shows a small window that says the program is working."""
        self._busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.check_button.state(state)
        self.build_button.state(state)
        self.configure(cursor="watch" if busy else "")
        if text:
            self.set_status(text)
        self._close_busy_window()
        if busy and notify:
            self._busy_window = self._show_busy_window(text)

    def _close_busy_window(self) -> None:
        """Stop the progress bar first: its Tcl timer would otherwise fire after the window, or the whole application,
        is gone ("cannot invoke winfo command: application has been destroyed")."""
        window, bar = getattr(self, "_busy_window", None), getattr(self, "_busy_bar", None)
        self._busy_window, self._busy_bar = None, None
        for widget, close in ((bar, "stop"), (window, "destroy")):
            if widget is not None:
                try:
                    getattr(widget, close)()
                except tk.TclError:
                    pass

    def _show_busy_window(self, text: str) -> tk.Toplevel:
        window = tk.Toplevel(self)
        window.title(APP_NAME)
        window.transient(self)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", lambda: None)  # it closes by itself when the work ends
        body = ttk.Frame(window, padding=(18, 14))
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=text, wraplength=420, justify="left").pack(anchor=tk.W)
        ttk.Label(body, text=tr(BUSY_NOTE), wraplength=420, justify="left", style="Note.TLabel").pack(anchor=tk.W, pady=(6, 10))
        bar = ttk.Progressbar(body, mode="indeterminate", length=420)
        bar.pack(fill=tk.X)
        bar.start(12)
        self._busy_bar = bar
        window.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - window.winfo_reqwidth()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - window.winfo_reqheight()) // 3)
        window.geometry(f"+{x}+{y}")
        return window

    def build(self) -> None:
        """Validate and assemble at once; the PowerShell syntax check (up to a few seconds) runs in a
        background thread so the window stays responsive; then the file is saved."""
        if self._busy:
            return
        result, issues = self.run_checks(with_powershell=False)
        if result is None or has_errors(issues):
            self._finish_build(result, issues)
            return
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["ps"] = check_scripts(result.scripts, self.paths.logs / "tmp")
            except Exception as exc:  # noqa: BLE001 - reported to the user, never lost in the thread
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="pscheck", daemon=True)
        self.set_busy(True, tr("Checking PowerShell syntax..."))
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(100, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                extra = [Issue("warning", "powershell", tr("PowerShell syntax check could not be run: {0}", outcome['error']))]
            else:
                extra = self._ps_issues(outcome["ps"])
            self._finish_build(result, issues + extra)

        self.after(100, poll)

    def _finish_build(self, result: BuildResult | None, issues: list[Issue]) -> None:
        self.show_issues(issues)
        if result is None or has_errors(issues):
            count = sum(1 for i in issues if i.level == "error")
            self.set_status(tr("Build stopped: {0} errors", count))
            self._dialog(messagebox.showerror, APP_NAME, tr("Build stopped: {0} errors. See the list at the bottom of the window; double-click an item to go to the error.", count), parent=self)
            return
        initial_dir = self._last_output.parent if self._last_output else self.paths.output
        name = self._dialog(filedialog.asksaveasfilename, parent=self, title=tr("Save answer file"), initialdir=str(initial_dir),
                                            initialfile="autounattend.xml", defaultextension=".xml",
                                            filetypes=[(tr("Windows answer file"), "*.xml")])
        if not name:
            self.set_status(tr("Build complete but not saved"))
            return
        path = Path(name)
        try:
            self.write_build(result, path)
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not write the file:\n{0}", exc), parent=self)
            return
        note = "" if path.name.lower() == "autounattend.xml" else tr("\n\nWarning: Windows Setup looks only for a file named autounattend.xml.")
        self.show_issues(issues + [Issue("info", "build", tr("Saved: {0} ({1} rules)", path, len(result.rule_ids)))])
        self.set_status(tr("Built: {0}", path))
        if self._dialog(messagebox.askyesno, 
            APP_NAME,
            tr("File saved:\n{0}\n\nRules enabled: {1}.\nCopy it to the root of a USB drive with the Windows 11 installation image and boot the PC from it.{2}\n\nOpen the folder containing the file?", path, len(result.rule_ids), note),
            parent=self,
        ):
            self._open_folder(path.parent)
