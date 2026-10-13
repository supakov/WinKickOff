"""The ADMX menu of the main window: imports of policy templates and catalog files, export, rename, show
or hide, delete; a change of the loaded templates rebuilds the window.

Methods of MainWindow (ui/main_window.py); the attributes they use are made there."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Any

from winkickoff import APP_NAME
from winkickoff.core.catalog import IMPORTED_PREFIX, Catalog
from winkickoff.core import admx as admx_module
from winkickoff.core import package as package_module
from winkickoff.core.i18n import available_languages, language, tr
from winkickoff.core.validate import Issue
from winkickoff.ui.window_common import error_text


class AdmxActions:
    """The ADMX menu: imports of templates and catalog files, export, rename, show or hide, delete."""

    # ----------------------------------------------------------------- imported templates (ADMX)

    def _restart(self, item: str | None = None, issues: list[Issue] | None = None, status: str = "") -> None:
        """Rebuild the window with another catalog (templates shown or hidden), keeping the open profile."""
        self.restart_state = {"profile": self.profile, "dirty": self.dirty, "item": item or self._current_item,
                              "issues": issues or [], "status": status, "splash": tr("Loading the imported templates...")}
        self.destroy()

    def import_templates(self, system: bool) -> None:
        """Read ADMX and ADML files in a background thread, keep them in admx/ and show them as a new subtree.
        Only reading: the templates of this Windows are its PolicyDefinitions folder."""
        if self._busy:
            return
        if system:
            folder = admx_module.system_folder()
        else:
            chosen = self._dialog(filedialog.askdirectory, parent=self, mustexist=True,
                                             title=tr("Folder with ADMX templates and their language folders"))
            if not chosen:
                return
            folder = Path(chosen)
        if not folder.is_dir() or not any(folder.glob("*.admx")):
            self._dialog(messagebox.showerror, APP_NAME, tr("There are no ADMX templates in {0}.", folder), parent=self)
            return
        replace = None
        existing = admx_module.find_imports(self.paths.admx, folder)
        if existing:
            answer = self._dialog(messagebox.askyesnocancel, APP_NAME, tr(
                "The templates of {0} are already imported as \"{1}\".\n\n"
                "Yes: update that import; its tree and the choices in profiles stay.\n"
                "No: add one more tree; the policies it shares with the other are shown in both with one check mark.\n"
                "Cancel: do not import.", folder, existing[-1].name), parent=self)
            if answer is None:
                return
            replace = existing[-1] if answer else None
        codes = list(available_languages(self.paths.resources, self.paths.rules))
        outcome: dict[str, Any] = {}
        progress = {"done": 0, "total": 0}

        def work() -> None:
            try:
                outcome["data"] = admx_module.read_templates(folder, codes, progress=lambda done, total: progress.update(done=done, total=total))
            except Exception as exc:  # noqa: BLE001 - reported to the user, never lost in the thread
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="admx", daemon=True)
        self.set_busy(True, tr("Reading templates from {0}...", folder), notify=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                if progress["total"]:
                    self.set_status(tr("Reading templates: {0} of {1}", progress["done"], progress["total"]))
                self.after(150, poll)
                return
            self.set_busy(False)
            self.finish_import(folder, system, outcome, replace)

        self.after(150, poll)

    def finish_import(self, folder: Path, system: bool, outcome: dict[str, Any],
                      replace: admx_module.ImportInfo | None = None) -> None:
        if "error" in outcome:
            self._dialog(messagebox.showerror, APP_NAME, tr("The templates were not imported:\n{0}", outcome["error"]), parent=self)
            return
        data = outcome["data"]
        try:
            info = admx_module.save_import(self.paths.admx, folder, data, system=system, replace=replace)
        except (OSError, ValueError) as exc:  # ValueError: AdmxError of the record check, an encoding error
            self._dialog(messagebox.showerror, APP_NAME, tr("The imported templates were not saved:\n{0}", error_text(exc)),
                         parent=self)
            return
        issues = [Issue("info", "", tr("Not imported: {0} policies with {1}", count, reason)) for reason, count in admx_module.skip_summary(data)]
        issues += [Issue("warning", "", tr("Template file not read: {0}", problem)) for problem in data.get("problems", [])[:50]]
        self.settings.admx = [i for i in self.settings.admx if i != info.id] + [info.id]
        self.save_settings()
        text = tr("Imported templates \"{0}\" updated: {1} policies, {2} skipped", info.name, info.policies, info.skipped) if replace \
            else tr("Imported templates \"{0}\": {1} policies, {2} skipped", info.name, info.policies, info.skipped)
        self._restart("g:" + IMPORTED_PREFIX + info.id, issues, text)

    def import_catalog_file(self, path: Path | None = None) -> None:
        """A catalog file (core/package.py: exported templates, plain or compressed), read and checked in a background
        thread, kept in admx/ and shown as a new subtree like imported templates."""
        if self._busy:
            return
        if path is None:
            chosen = self._dialog(filedialog.askopenfilename, parent=self, title=tr("Import a catalog file"),
                                  filetypes=[(tr("WinKickOff catalog"), "*.json *.json.gz *.json.xz"), (tr("All files"), "*.*")])
            if not chosen:
                return
            path = Path(chosen)
        replace = None
        existing = package_module.find_package_imports(self.paths.admx, path)
        if existing:
            answer = self._dialog(messagebox.askyesnocancel, APP_NAME, tr(
                "The catalog file {0} is already imported as \"{1}\".\n\n"
                "Yes: update that import; its tree and the choices in profiles stay.\n"
                "No: add one more tree; the policies it shares with the other are shown in both with one check mark.\n"
                "Cancel: do not import.", path.name, existing[-1].name), parent=self)
            if answer is None:
                return
            replace = existing[-1] if answer else None
        self._read_catalog(path, lambda package: package_module.import_package(self.paths.admx, path, package, replace=replace),
                           replace is not None)

    def import_bundled_catalog(self, catalog: package_module.BundledCatalog) -> None:
        """A catalog that ships with the program; importing it again updates the same tree."""
        if self._busy:
            return
        updated = catalog.import_id in {info.id for info in admx_module.list_imports(self.paths.admx)}
        self._read_catalog(catalog.path, lambda package: package_module.import_bundled(self.paths.admx, catalog, package),
                           updated)

    def _read_catalog(self, path: Path, store: Any, updated: bool) -> None:
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["package"] = package_module.read_package(path)
            except Exception as exc:  # noqa: BLE001 - reported to the user, never lost in the thread
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="catalog", daemon=True)
        self.set_busy(True, tr("Reading the catalog file {0}...", path.name), notify=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            self.finish_catalog(outcome, store, updated)

        self.after(150, poll)

    def finish_catalog(self, outcome: dict[str, Any], store: Any, updated: bool) -> None:
        if "error" in outcome:
            self._dialog(messagebox.showerror, APP_NAME, tr("The catalog was not imported:\n{0}", error_text(outcome["error"])),
                         parent=self)
            return
        try:
            info = store(outcome["package"])
        except (OSError, ValueError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The imported templates were not saved:\n{0}", error_text(exc)),
                         parent=self)
            return
        issues = [Issue("info", "", tr("Not imported: {0} policies with {1}", count, reason))
                  for reason, count in admx_module.skip_summary(outcome["package"].templates)]
        self.settings.admx = [i for i in self.settings.admx if i != info.id] + [info.id]
        self.save_settings()
        text = tr("Catalog \"{0}\" updated: {1} policies, {2} skipped", info.name, info.policies, info.skipped) if updated \
            else tr("Catalog \"{0}\" imported: {1} policies, {2} skipped", info.name, info.policies, info.skipped)
        self._restart("g:" + IMPORTED_PREFIX + info.id, issues, text)

    def export_templates(self, import_id: str, name: str) -> None:
        """Write a saved import as a catalog file that another WinKickOff imports (menu ADMX)."""
        chosen = self._dialog(filedialog.asksaveasfilename, parent=self, title=tr("Export imported templates"),
                              defaultextension=".json", initialfile=package_module.package_id(name) + ".json",
                              filetypes=[(tr("WinKickOff catalog"), "*.json")])
        if not chosen:
            return
        try:
            package_module.export_package(self.paths.admx, import_id, Path(chosen))
        except (OSError, ValueError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The imported templates were not exported:\n{0}", error_text(exc)),
                         parent=self)
            return
        self.set_status(tr("Imported templates \"{0}\" exported to {1}", name, chosen))

    def rename_templates(self, import_id: str, name: str) -> None:
        """A name of the user's choice for an imported tree; an update of the import keeps it."""
        if self._busy:
            return
        new = self._dialog(simpledialog.askstring, APP_NAME, tr("New name of the imported tree:"), initialvalue=name, parent=self)
        if new is None or " ".join(new.split()) == name:
            return
        try:
            info = admx_module.rename_import(self.paths.admx, import_id, new)
        except (OSError, admx_module.AdmxError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The name was not changed:\n{0}", error_text(exc)), parent=self)
            return
        shown = import_id in self.settings.admx
        self._restart("g:" + IMPORTED_PREFIX + import_id if shown else None, status=tr("Imported tree renamed: \"{0}\"", info.name))

    def show_templates(self, import_id: str, shown: bool, item: str | None = None) -> None:
        """Show or hide a saved import; the choice is remembered for the next start. item: the node to open then
        (by default the shown tree)."""
        if self._busy:  # a rebuild would drop the work of the background thread; the check box shows the setting again
            var = getattr(self, "import_vars", {}).get(import_id)
            if var is not None:
                var.set(import_id in self.settings.admx)
            return
        wanted = [i for i in self.settings.admx if i != import_id] + ([import_id] if shown else [])
        if wanted == self.settings.admx:
            return
        self.settings.admx = wanted
        self.save_settings()
        self._restart(item or ("g:" + IMPORTED_PREFIX + import_id if shown else None))

    def delete_templates(self, import_id: str, name: str) -> None:
        if self._busy:
            return
        if not self._dialog(messagebox.askyesno, APP_NAME, tr("Delete the imported templates \"{0}\" from the program folder? Profiles "
                                                "keep the choices made in them.", name), parent=self):
            return
        try:
            admx_module.delete_import(self.paths.admx, import_id)
        except (OSError, admx_module.AdmxError) as exc:
            self._dialog(messagebox.showerror, APP_NAME, tr("The imported templates were not deleted:\n{0}", error_text(exc)), parent=self)
            return
        self.settings.admx = [i for i in self.settings.admx if i != import_id]
        self.save_settings()
        self._restart(status=tr("Imported templates \"{0}\" deleted", name))
