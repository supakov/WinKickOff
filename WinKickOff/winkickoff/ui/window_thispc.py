"""The menu "This PC" of the main window (tasks T15, T25, T26): check, read, apply, return to Windows
defaults; nothing here runs without the person's choice, and the tests replace run_audit and the
elevation.

Methods of MainWindow (ui/main_window.py); the attributes they use are made there."""

from __future__ import annotations

import logging
import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.apply import (
    ApplyPlan,
    RevertPlan,
    audit_rules,
    parse_audit_report,
    plan_apply,
    plan_revert,
    render_apply,
    render_audit,
    render_revert,
    render_undo,
    run_audit,
    status_title,
    write_script,
)
from winkickoff.core.capture import capture_profile, render_capture, summary_lines
from winkickoff.core import apply as apply_module
from winkickoff.core.i18n import tr
from winkickoff.core.profile import Profile
from winkickoff.core.validate import Issue
from winkickoff.ui.window_common import (
    READ_PC_TIMEOUT,
    READ_SELECTION_NOTE,
    READ_PC_ADMIN_NOTE,
    READ_PC_NOTE,
    rule_of,
)

log = logging.getLogger(__name__)


class ThisPcActions:
    """The menu "This PC": check, read into a profile, apply, return to Windows defaults."""

    # ----------------------------------------------------------------- this PC (task T15)

    def _fill_pc_menu(self, menu: tk.Menu) -> None:
        # Always available: the first apply or return asks for permission (toggle_allow_apply) instead of a
        # greyed-out item whose switch is hard to find.
        menu.add_command(label=tr("Check the selection on this PC"), command=self.audit_selected)
        menu.add_command(label=tr("Read the selection on this PC into the open profile..."), command=self.read_selection)
        menu.add_command(label=tr("Save an apply script for the selection..."), command=self.save_apply_scripts)
        menu.add_command(label=tr("Apply the selection now..."), command=self.apply_now)
        menu.add_command(label=tr("Return the selection to Windows defaults now..."), command=self.revert_now)

    def _on_tree_right_click(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        item = self.tree.identify_row(event.y)
        if not (item.startswith("r:") or item.startswith("g:")):
            return None
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def toggle_allow_apply(self) -> None:
        wanted = bool(self.allow_apply_var.get())
        if wanted and not self._dialog(messagebox.askyesno, APP_NAME, tr(
                "Allow applying rules to this computer?\n\nThe apply script changes the registry, services "
                "and Windows components. Test it on a test computer or a virtual machine first. App "
                "removal and PowerShell steps cannot be rolled back automatically. Applying always starts "
                "through a User Account Control prompt."),
                icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            self.allow_apply_var.set(False)
            wanted = False
        self.settings.allow_apply = wanted
        self.settings.save(self.paths.settings_file)

    def _ensure_apply_allowed(self) -> bool:
        """Changes to this PC need the permission of "This PC, Allow applying on this PC"; ask for it once."""
        if self.settings.allow_apply:
            return True
        self.allow_apply_var.set(True)
        self.toggle_allow_apply()
        return self.settings.allow_apply

    def _apply_items(self) -> list[str]:
        items = ["r:" + rule_of(i) if i.startswith("r:") else i for i in self.tree.selection() if i.startswith(("r:", "g:"))]
        if not items:
            self._dialog(messagebox.showinfo, APP_NAME, tr("Select a rule or a group in the tree."), parent=self)
        return items

    def _plan_issues(self, plan: ApplyPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("not applied: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.requirement:
                notes.append(tr("needed by a selected rule"))
            if planned.irreversible:
                notes.append(tr("not rolled back automatically"))
            if planned.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if planned.irreversible else "info"
            issues.append(Issue(level, planned.rule.id, tr("will be applied") + (": " + "; ".join(notes) if notes else "")))
        for returning in plan.reverts:
            notes = [tr("disabled in the profile")]
            if returning.dependent:
                notes.append(tr("depends on a selected rule"))
            if returning.skipped:
                notes.append(tr("not returned automatically: {0}", ", ".join(sorted({a.type for a in returning.skipped}))))
            if returning.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if returning.skipped else "info"
            issues.append(Issue(level, returning.rule.id, tr("will be returned to Windows defaults") + ": " + "; ".join(notes)))
        if plan.not_configured:
            issues.append(Issue("info", "", tr("{0} imported policies without a check mark are not configured and stay as they are", plan.not_configured)))
        return issues

    def _nothing_to_apply(self, plan: ApplyPlan) -> None:
        """Say plainly why nothing happens, instead of a line in the status bar only."""
        reasons = [f"{self.rule_title(rule.id)}: {tr(reason)}" for rule, reason in plan.excluded[:8]]
        if plan.not_configured:
            reasons.append(tr("{0} imported policies without a check mark are not configured and stay as they are", plan.not_configured))
        more = tr("\n... and {0} more", len(plan.excluded) - 8) if len(plan.excluded) > 8 else ""
        self._dialog(messagebox.showinfo, APP_NAME, tr("There is nothing in the selection to apply to this computer.") + "\n\n"
                            + "\n".join(reasons) + more, parent=self)
        self.set_status(tr("The selection has no rules that can be applied to a running system"))

    def audit_selected(self) -> None:
        """Read-only check on this PC: which of the selected rules already take effect."""
        if self._busy:
            return
        items = self._apply_items()
        if not items:
            return
        rule_ids, skipped = audit_rules(self.catalog, items)
        excluded = [Issue("info", rule.id, tr("not checked: {0}", tr(reason))) for rule, reason in skipped]
        if not rule_ids:
            self.show_issues(excluded)
            self.set_status(tr("The selection has no rules that can be checked on a running system"))
            return
        script = render_audit(rule_ids, self.profile, self.catalog, self.paths.templates, APP_VERSION)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["text"] = run_audit(script, self.paths.logs / "tmp")
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="audit", daemon=True)
        self.set_busy(True, tr("Checking this PC (read-only)..."), notify=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                self.show_issues([Issue("error", "audit", tr("The check failed: {0}", outcome["error"]))] + excluded)
                self.set_status(tr("The check on this PC failed"))
                return
            self.show_audit(outcome["text"], excluded)

        self.after(150, poll)

    def toggle_mcp_read_pc(self) -> None:
        """The MCP option of read_this_pc: a client may read this computer (read only). Never saved: off at every start."""
        if self.service is None:
            return
        allowed = bool(self.mcp_read_pc_var.get())
        self.service.set_read_pc(allowed)
        self.set_status(tr("MCP clients may read the settings of this PC (read only)") if allowed
                        else tr("MCP clients may not read the settings of this PC"))

    def read_this_pc(self, elevated: bool = False) -> None:
        """Read the settings of this computer into a new profile (read only, core/capture.py): a reference PC to clone, or
        a damaged one to study. elevated: as administrator through one UAC prompt, so that features, capabilities and the
        apps of every user are read too."""
        if self._busy or not self.confirm_discard():
            return
        note = tr(READ_PC_NOTE) + ("\n\n" + tr(READ_PC_ADMIN_NOTE) if elevated else "")
        if not self._dialog(messagebox.askokcancel, APP_NAME, note, parent=self):
            return
        base = self.profile.copy()
        script = render_capture(self.catalog, base, self.paths.templates, APP_VERSION)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                runner = apply_module.run_audit_elevated if elevated else run_audit
                outcome["text"] = runner(script, self.paths.logs / "tmp", timeout=READ_PC_TIMEOUT)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="read-pc", daemon=True)
        self.set_busy(True, tr("Reading the settings of this PC (read-only)..."), notify=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            try:
                if "error" in outcome:
                    raise ValueError(str(outcome["error"]))
                profile, summary = capture_profile(self.catalog, base, outcome["text"], self.resources.keyboards)
            except ValueError as exc:
                self.show_issues([Issue("error", "audit", tr("The read of this PC failed: {0}", exc))])
                self.set_status(tr("The read of this PC failed"))
                return
            self.adopt_profile(profile, [Issue(*line) for line in summary_lines(summary, self.rule_title)])
            self.set_status(tr("The settings of {0} are in a new profile: check it and save it under a name",
                               summary.computer or tr("this PC")))

        self.after(150, poll)

    def read_selection(self) -> None:
        """Read the selected rules or catalog on this computer into the open profile, as unsaved changes (read only)."""
        if self._busy:
            return
        items = self._apply_items()
        if not items:
            return
        only = apply_module.selected_rules(self.catalog, items)
        if not self._dialog(messagebox.askokcancel, APP_NAME, tr(READ_SELECTION_NOTE, len(only)), parent=self):
            return
        base = self.profile.copy()
        script = render_capture(self.catalog, base, self.paths.templates, APP_VERSION, only=only)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["text"] = run_audit(script, self.paths.logs / "tmp", timeout=READ_PC_TIMEOUT)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="read-selection", daemon=True)
        self.set_busy(True, tr("Reading the settings of this PC (read-only)..."), notify=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            try:
                if "error" in outcome:
                    raise ValueError(str(outcome["error"]))
                profile, summary = capture_profile(self.catalog, base, outcome["text"], self.resources.keyboards, only=only)
            except ValueError as exc:
                self.show_issues([Issue("error", "audit", tr("The read of this PC failed: {0}", exc))])
                self.set_status(tr("The read of this PC failed"))
                return
            changed = len(profile.diff(self.profile, self.catalog))
            self.set_profile(profile, dirty=self.dirty or changed > 0)
            self.show_issues([Issue(*line) for line in summary_lines(summary, self.rule_title)])
            self.set_status(tr("The selection was read from this PC into the open profile: {0} changes, not saved", changed))

        self.after(150, poll)

    def adopt_profile(self, profile: Profile, issues: list[Issue]) -> None:
        """Open a profile made in memory (the read of this PC) as a new profile with unsaved changes."""
        profile.path = None
        self.set_profile(profile, dirty=True)
        self.show_issues(issues)

    def show_audit(self, report_text: str, excluded: list[Issue]) -> None:
        meta, results = parse_audit_report(report_text)
        issues: list[Issue] = []
        counts = {"applied": 0, "not-applied": 0, "partial": 0, "unknown": 0}
        for rule_id, result in results.items():
            counts[result.status] = counts.get(result.status, 0) + 1
            details = [f"{c['check']}: {c['current'] or tr("no value")} ({tr("expected")} {c['expected']})"
                       for c in result.checks if c["status"] == "differs"][:3]
            level = "info" if result.status in ("applied", "unknown") else "warning"
            issues.append(Issue(level, rule_id, status_title(result.status) + (": " + "; ".join(details) if details else "")))
        self.show_issues(issues + excluded)
        note = "" if str(meta.get("admin")).lower() == "true" else tr(" Without administrator rights some checks are unavailable.")
        self.set_status(tr("Check on this PC: in effect {0}, not in effect {1}, partly {2}, not checked {3}.",
                           counts["applied"], counts["not-applied"], counts["partial"], counts["unknown"]) + note)

    def _write_apply_folder(self, folder: Path, plan: ApplyPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        apply_path = folder / "Apply.ps1"
        write_script(apply_path, render_apply(plan, self.profile, self.catalog, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("WinKickOff {0} apply scripts, profile \"{1}\".", APP_VERSION, tr(self.profile.name)), "",
                 tr("1. Test on a test computer or a virtual machine first."),
                 tr("2. Run Apply.ps1 as administrator: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. The log and the backup of the previous values appear next to the script (apply-*.log, backup-*.json)."),
                 tr("4. Rollback: Undo-Apply.ps1 as administrator. Removed apps and PowerShell steps are not rolled back."),
                 tr("5. Restart the computer after applying."), "", tr("Rules:")]
        for planned in plan.rules:
            flags = (tr(" (not rolled back)") if planned.irreversible else "") + (tr(" (restart needed)") if planned.reboot else "")
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.reverts:
            lines += ["", tr("Off in the profile, returning to the Windows defaults:")]
            for returning in plan.reverts:
                lines.append(f"- {returning.rule.id}: {self.rule_title(returning.rule.id)}" + (tr(" (partly)") if returning.skipped else ""))
        if plan.excluded:
            lines += ["", tr("Not applied:")]
            lines += [f"- {rule.id}: {tr(reason)}" for rule, reason in plan.excluded]
        (folder / "README.txt").write_bytes(("\n".join(lines) + "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        return apply_path

    def save_apply_scripts(self) -> Path | None:
        items = self._apply_items()
        if not items:
            return None
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if plan.empty:
            self._nothing_to_apply(plan)
            return None
        name = self._dialog(filedialog.askdirectory, parent=self, title=tr("Folder for the apply scripts"), initialdir=str(self.paths.output))
        if not name:
            return None
        folder = Path(name) / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            self._write_apply_folder(folder, plan)
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The scripts were not written:\n{0}", exc), parent=self)
            return None
        self.set_status(tr("Apply scripts saved: {0} (rules: {1})", folder, len(plan.rules) + len(plan.reverts)))
        return folder

    def apply_now(self, rule_items: list[str] | None = None) -> bool:
        """Apply the selection (or rule_items, the changed rules of a comparison) to this PC: confirmation, scripts in
        logs/, launch through UAC."""
        items = rule_items if rule_items else self._apply_items()
        if not items or not self._ensure_apply_allowed():
            return False
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if plan.empty:
            self._nothing_to_apply(plan)
            return False
        irreversible = [self.rule_title(p.rule.id) for p in plan.rules if p.irreversible]
        text = tr("Apply the selected rules ({1}) to computer {0}?", os.environ.get("COMPUTERNAME", "?"), len(plan.rules) + len(plan.reverts))
        if plan.reverts:
            text += "\n\n" + tr("On in the profile and applied: {0}. Off in the profile and returned to the Windows defaults: {1}.",
                                len(plan.rules), len(plan.reverts))
        if irreversible:
            text += "\n\n" + tr("Not rolled back automatically: {0}.", "; ".join(irreversible[:8]) + ("..." if len(irreversible) > 8 else ""))
        if any(p.reboot for p in plan.rules) or any(p.reboot for p in plan.reverts):
            text += "\n\n" + tr("A restart is needed after applying.")
        text += "\n\n" + tr("Windows will ask to confirm administrator rights. The previous values are saved for rollback (Undo-Apply.ps1).")
        if not self._dialog(messagebox.askyesno, APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            script = self._write_apply_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Applying was not started:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("The apply script was started; log and backup: {0}", folder))
        return True

    def _revert_issues(self, plan: RevertPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("not returned: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.dependent:
                notes.append(tr("depends on a selected rule"))
            if planned.skipped:
                notes.append(tr("not returned automatically: {0}", ", ".join(sorted({a.type for a in planned.skipped}))))
            if planned.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if planned.skipped else "info"
            issues.append(Issue(level, planned.rule.id, tr("will be returned to Windows defaults") + (": " + "; ".join(notes) if notes else "")))
        if plan.not_configured:
            issues.append(Issue("info", "", tr("{0} imported policies of the selected groups stay as they are: select them one by one to return them to Windows defaults", plan.not_configured)))
        return issues

    def _write_revert_folder(self, folder: Path, plan: RevertPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        script_path = folder / "Apply.ps1"
        write_script(script_path, render_revert(plan, self.profile, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("Return to Windows defaults, WinKickOff {0}.", APP_VERSION), "",
                 tr("1. Test on a test computer or a virtual machine first."),
                 tr("2. Run Apply.ps1 as administrator: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. The log and the backup of the previous values appear next to the script (apply-*.log, backup-*.json)."),
                 tr("4. To undo the return: Undo-Apply.ps1 as administrator."),
                 tr("5. Restart the computer after applying."), "", tr("Rules:")]
        for planned in plan.rules:
            flags = tr(" (partly)") if planned.skipped else ""
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.excluded:
            lines += ["", tr("Not returned:")]
            lines += [f"- {rule.id}: {tr(reason)}" for rule, reason in plan.excluded]
        (folder / "README.txt").write_bytes(("\n".join(lines) + "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        return script_path

    def revert_now(self) -> bool:
        """Return the selected rules on this PC to the values of a clean Windows, through UAC, with a backup."""
        items = self._apply_items()
        if not items or not self._ensure_apply_allowed():
            return False
        plan = plan_revert(self.catalog, items)
        self.show_issues(self._revert_issues(plan))
        if not plan.rules:
            self.set_status(tr("The selection has no rules that can be returned to Windows defaults on a running system"))
            return False
        partial = [self.rule_title(p.rule.id) for p in plan.rules if p.skipped]
        text = tr("Return the selected rules ({1}) on computer {0} to Windows defaults?",
                  os.environ.get("COMPUTERNAME", "?"), len(plan.rules))
        dependents = [self.rule_title(p.rule.id) for p in plan.rules if p.dependent]
        if dependents:
            text += "\n\n" + tr("Together with them: {0}.", "; ".join(dependents[:8]) + ("..." if len(dependents) > 8 else ""))
        if partial:
            text += "\n\n" + tr("Not returned completely (apps, scripts, values with an unknown default): {0}.",
                                "; ".join(partial[:8]) + ("..." if len(partial) > 8 else ""))
        text += "\n\n" + tr("Windows will ask to confirm administrator rights. The previous values are saved for rollback (Undo-Apply.ps1).")
        if not self._dialog(messagebox.askyesno, APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("revert-%Y%m%d-%H%M%S")
        try:
            script = self._write_revert_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The return was not started:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("The return-to-defaults script is running; log and backup: {0}", folder))
        return True

    def open_output_folder(self) -> None:
        self._open_folder(self._last_output.parent if self._last_output else self.paths.output)

    def _open_folder(self, folder: Path) -> None:
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("Could not open the folder:\n{0}", exc), parent=self)
