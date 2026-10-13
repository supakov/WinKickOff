"""Policy templates (ADMX files with their ADML translations) imported as catalog rules.

An import reads every *.admx of a folder (by default the PolicyDefinitions folder of this Windows) and the ADML
files of the wanted languages, keeps what the rules need in <program folder>/admx/<id>/ (import.json: name,
source, counts; policies.json: the policies), and turns the policies into the rules of a subtree
"admx.<id>" in the interface language. Every text of that subtree comes from the ADML files; en-US is the
fallback.

A policy becomes:
- one rule with the parameter "state" (Enabled or Disabled) when both states set the same single value;
- otherwise a rule for the Enabled state with the policy elements as parameters, plus a rule for the Disabled
  state when that state writes values; the two rules conflict.
A list element (a key with a variable number of values) becomes a parameter of type "list" and a reg-list
action: value names are the data itself, valuePrefix with a number, or given by each item ("name=value") for
explicitValue; a list that is not additive deletes the other values of its key first, and the Disabled rule
leaves the key without values, as Group Policy does. A multiText element is a "list" parameter written as one
MultiString value.
Machine policies write HKLM in the specialize pass; user policies write the default user profile (DU:), so
every account created during installation gets them. Rule ids follow the template namespace and the policy
name ("admx.<namespace>.<policy>"), so a profile keeps its choices across imports of the same templates.
Policies with value lists inside an option or unsafe characters are skipped and counted with the reason.

Template files are untrusted data: documents with a DTD or entities are refused, files and folders have size
limits, and keys, value names and strings with control characters, "$", backquotes, double quotes, typographic
quotes or "]]>" are refused, because they end up inside PowerShell strings and CDATA sections.

The package: base (constants, limits, XML helpers), templates (ADMX and ADML to records), check (check_templates,
conform), store (admx/<id>/ next to the program), rules (records to catalog rules, with_imports).
"""

from __future__ import annotations

from winkickoff.core.admx.base import (
    FORMAT_VERSION,
    READ_FORMATS,
    LEGACY_SKIPS,
    META_FILE,
    DATA_FILE,
    SOURCE_CULTURE,
    MAX_FILES,
    MAX_FILE_BYTES,
    MAX_DWORD,
    MAX_QWORD,
    IMPORT_ID_RE,
    SKIP_REASONS,
    SIDE_TITLES,
    NO_CATEGORY,
    IMPORTED_RISK,
    STATE_TITLE,
    STATE_ENABLED,
    STATE_DISABLED,
    TITLE_ENABLED,
    TITLE_DISABLED,
    ON,
    OFF,
    VALUE,
    NO_EXPLAIN,
    AdmxError,
    read_xml,
    safe_name,
    safe_key,
    safe_value,
)
from winkickoff.core.admx.check import (
    MAX_POLICIES,
    MAX_ELEMENTS,
    MAX_WRITES,
    MAX_OPTIONS,
    MAX_TEXT,
    MAX_TEXTS,
    MAX_CATEGORY_DEPTH,
    WRITE_KINDS,
    POLICY_CLASSES,
    check_templates,
    without_paths,
    conform,
)
from winkickoff.core.admx.templates import adml_cultures, pick, read_templates
from winkickoff.core.admx.store import (
    ImportInfo,
    MAX_NAME,
    trust_order,
    check_name,
    fit_name,
    system_folder,
    new_import_id,
    same_folder,
    find_imports,
    save_import,
    store_import,
    rename_import,
    MAX_META_BYTES,
    MAX_RECORDS_BYTES,
    list_imports,
    load_import,
    delete_import,
)
from winkickoff.core.admx.rules import (
    policy_rules,
    policy_ids,
    has_policy,
    ImportedPart,
    catalog_part,
    with_imports,
    skip_summary,
)

__all__ = [
    "FORMAT_VERSION",
    "READ_FORMATS",
    "LEGACY_SKIPS",
    "META_FILE",
    "DATA_FILE",
    "SOURCE_CULTURE",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_DWORD",
    "MAX_QWORD",
    "IMPORT_ID_RE",
    "SKIP_REASONS",
    "SIDE_TITLES",
    "NO_CATEGORY",
    "IMPORTED_RISK",
    "STATE_TITLE",
    "STATE_ENABLED",
    "STATE_DISABLED",
    "TITLE_ENABLED",
    "TITLE_DISABLED",
    "ON",
    "OFF",
    "VALUE",
    "NO_EXPLAIN",
    "AdmxError",
    "read_xml",
    "safe_name",
    "safe_key",
    "safe_value",
    "MAX_POLICIES",
    "MAX_ELEMENTS",
    "MAX_WRITES",
    "MAX_OPTIONS",
    "MAX_TEXT",
    "MAX_TEXTS",
    "MAX_CATEGORY_DEPTH",
    "WRITE_KINDS",
    "POLICY_CLASSES",
    "check_templates",
    "without_paths",
    "conform",
    "adml_cultures",
    "pick",
    "read_templates",
    "ImportInfo",
    "MAX_NAME",
    "trust_order",
    "check_name",
    "fit_name",
    "system_folder",
    "new_import_id",
    "same_folder",
    "find_imports",
    "save_import",
    "store_import",
    "rename_import",
    "MAX_META_BYTES",
    "MAX_RECORDS_BYTES",
    "list_imports",
    "load_import",
    "delete_import",
    "policy_rules",
    "policy_ids",
    "has_policy",
    "ImportedPart",
    "catalog_part",
    "with_imports",
    "skip_summary",
]
