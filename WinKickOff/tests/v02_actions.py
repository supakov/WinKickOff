"""Test helpers for the hand-written v0.2 answer file over winkickoff.core.actions_parser.

The file lives in the appendices of the documentation: docs/appendices/B-autounattend-v0.2/.

The semantic golden tests compare normalised action tuples: every registry write and removal,
service start type, command, component and app of Setup-System.ps1 v0.2 must be present in the
catalog with the same value. The parser itself lives in the application (the importer uses it).

v0.2 is frozen, the catalog defaults (and so the "Office" preset) move on. reference_profile()
restores v0.2 from the defaults: V02_DIFFERENCES lists every rule whose default differs from v0.2.
A new rule that is on by default must be added here as off, otherwise the import and coverage tests fail.
"""

from __future__ import annotations

from pathlib import Path

from winkickoff.core.actions_parser import Action, catalog_actions, extract_script, parse_script, rule_actions
from winkickoff.core.catalog import Catalog
from winkickoff.core.profile import Profile

REPO = Path(__file__).resolve().parents[2]
V02 = REPO / "docs" / "appendices" / "B-autounattend-v0.2" / "autounattend.xml"

# rule id -> state in v0.2, for every rule whose catalog default differs from v0.2
V02_DIFFERENCES: dict[str, bool] = {
    # 26.09.2026, commit d33fc41: the "Office" preset chosen in the repository
    "update.other-microsoft-products": True,
    "asr.usb-untrusted": True,
    **{rule_id: False for rule_id in (
        "edge.diagnostic-data-off", "edge.search-telemetry-off", "edge.shopping-off", "edge.rewards-off",
        "edge.insider-promo-off", "edge.translate-off", "edge.feedback-off", "edge.autofill-cards-off",
        "chrome.metrics-off", "chrome.variations", "chrome.background-off", "chrome.genai-off",
        "chrome.genai-local-model-off", "chrome.devtools-genai-off", "chrome.translate-off", "chrome.cast-private-only",
        "chrome.promotions-off", "chrome.autofill-cards-off",
        "brave.rewards-off", "brave.wallet-off", "brave.vpn-off", "brave.ai-chat-off", "brave.stats-ping-off",
        "brave.p3a-off", "brave.news-off", "brave.talk-off", "brave.playlist-off", "brave.speedreader-off",
        "brave.wayback-off", "brave.web-discovery-off", "brave.translate-off", "brave.tor-off",
    )},
    # 28.09.2026, customer list MoreOptions (AI, telemetry, advertising, search, speech, Office, OneDrive, drivers),
    # Edge AI policies with browser sign-in and the sidebar off, the Gallery hidden in File Explorer
    **{rule_id: False for rule_id in (
        "ai.recall-user-off", "ai.settings-agent-off", "ai.agent-connectors-off",
        "ai.apps-generative-off", "ai.copilot-microphone-off", "ai.paint-off",
        "ai.notepad-off", "ai.copilot-pin-screen-off", "ai.typing-insights-off",
        "telemetry.settings-state", "telemetry.user-policy", "telemetry.change-notification-off",
        "telemetry.limit-logs-dumps", "telemetry.app-telemetry-off", "telemetry.steps-recorder-off",
        "telemetry.app-diagnostics-off", "telemetry.feedback-user-off", "ads.lock-screen-spotlight-off",
        "ads.suggestions-user-policies", "ads.account-notifications-off", "ads.advertising-id-user-off",
        "search.cloud-off", "search.user-cloud-off", "search.start-track-off",
        "speech.online-off", "speech.online-user-off", "speech.narrator-online-off",
        "speech.narrator-extensions-off", "drivers.coinstallers-off", "drivers.metadata-off",
        "onedrive.kfm-block", "onedrive.no-traffic-before-signin", "onedrive.feedback-off",
        "edge.sidebar-off", "edge.signin-off", "edge.genai-local-model-off",
        "edge.builtin-ai-apis-off", "edge.history-ai-search-off", "edge.ai-themes-off",
        "edge.text-prediction-off", "edge.tab-services-off", "edge.autofill-ml-off",
        "edge.copilot-address-bar-off", "edge.ntp-copilot-off", "edge.copilot-cowork-off",
        "edge.browsing-with-copilot-off", "edge.copilot-page-context-off", "edge.entra-copilot-page-context-off",
        "edge.m365-copilot-icon-off", "edge.compose-inline-off", "edge.copilot-search-history-off",
        "office.connected-ai-off", "office.optional-connected-off", "office.telemetry-off",
        "office.feedback-off", "office.copilot-checkbox-off", "nav.gallery-hidden",
    )},
    # 26.09.2026, customer requests: OneDrive is not installed; no UAC prompt for Task Manager
    "apps.remove.onedrive": False,
    "uac.admin-always-notify": True,
}


# (rule id, parameter) -> value in v0.2, for every parameter whose catalog default differs from v0.2
V02_PARAMS: dict[tuple[str, str], object] = {}


def reference_profile(catalog: Catalog) -> Profile:
    """The profile that reproduces the hand-written v0.2: catalog defaults with V02_DIFFERENCES and V02_PARAMS applied."""
    profile = Profile.from_catalog(catalog, name="v0.2")
    for rule_id, enabled in V02_DIFFERENCES.items():
        profile.rules[rule_id].enabled = enabled
    for (rule_id, name), value in V02_PARAMS.items():
        profile.set_param(rule_id, name, value)
    return profile


__all__ = [
    "REPO",
    "V02",
    "V02_DIFFERENCES",
    "V02_PARAMS",
    "reference_profile",
    "Action",
    "catalog_actions",
    "extract_script",
    "parse_script_actions",
    "parse_script_actions_ordered",
    "parse_v02_actions",
    "rule_actions",
]


def parse_v02_actions(source: Path | str) -> set[Action]:
    """Actions of Setup-System.ps1 embedded in an answer file (a path or the XML text itself)."""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    return parse_script(extract_script(text, "Setup-System.ps1")).action_set


def parse_script_actions(script: str) -> set[Action]:
    return parse_script(script).action_set


def parse_script_actions_ordered(script: str) -> list[Action]:
    return parse_script(script).actions
