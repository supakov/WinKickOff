# 18. Browsers: Microsoft Edge, Google Chrome, Brave

Browser policies from issue #1 of the repository ("Web Browsers debloat"). The issue attached three .cmd
scripts (`DebloatEdge.cmd`, `DebloatChrome.cmd`, `DebloatBrave.cmd`); every policy name and value was checked
on 25.09.2026 against the vendors' definitions (see Sources). WinKickOff turns each working policy into a
separate rule of the «Браузеры» (Browsers) section, so any of them can be disabled. The rules are generated
by `WinKickOff/tools/make_browser_rules.py`.

All rules write machine policies (`HKLM`) in the specialize pass, apply to every user and cannot be changed
by users in the browser settings. A policy of a browser that is not installed has no effect. Since
26.09.2026 (commit d33fc41) a part of the rules is on by default and so in every preset built from the
defaults: telemetry, advertising, shopping and rewards, AI features, page translation, card autofill, the
Brave wallet, VPN, news, Tor and the like (`DEFAULT_ON` in `WinKickOff/tools/make_browser_rules.py`). Sync,
browser sign-in, the Edge sidebar and web capture, search suggestions, address autofill, the Chrome Lens
overlay and built-in DNS client and the password managers stay off. The two Edge
rules of v0.2 (`edge.smartscreen-locked`, `edge.baseline`, card 10) moved into the same section and stay on.

## Microsoft Edge

Key: `HKLM\SOFTWARE\Policies\Microsoft\Edge`, all values REG_DWORD.

| Rule | Value | Effect | Edge |
|---|---|---|---|
| `edge.diagnostic-data-off` | `DiagnosticData = 0` | No required or optional diagnostic data is sent to Microsoft; replaces the obsolete `MetricsReportingEnabled` and `SendSiteInfoToImproveServices` of the script | 122+ (Windows 10/11) |
| `edge.search-telemetry-off` | `Edge3PSerpTelemetryEnabled = 0` | No telemetry about searches on third-party search engines | 120+ |
| `edge.sidebar-off` | `HubsSidebarEnabled = 0` | The sidebar is never shown; before Edge 141 this also hides the Copilot button | 99+ |
| `edge.shopping-off` | `EdgeShoppingAssistantEnabled = 0` | No price comparison, coupons or cashback on shop pages | 87+ |
| `edge.rewards-off` | `ShowMicrosoftRewards = 0` | Microsoft Rewards hidden and switched off | 88+ |
| `edge.insider-promo-off` | `MicrosoftEdgeInsiderPromotionEnabled = 0` | No offers to install Edge Insider builds | 98+ |
| `edge.sync-off` | `SyncDisabled = 1` | Sync of favorites, passwords, history and settings is off | 77+ |
| `edge.translate-off` | `TranslateEnabled = 0` | No page translation offers; page text is not sent to the translator | 77+ |
| `edge.web-capture-off` | `WebCaptureEnabled = 0` | Web capture unavailable | 87+ |
| `edge.autofill-address-off` | `AutofillAddressEnabled = 0` | Addresses are not saved or filled in | 77+ |
| `edge.search-suggest-off` | `SearchSuggestEnabled = 0` | No search suggestions in the address bar | 77+ |
| `edge.feedback-off` | `UserFeedbackAllowed = 0` | The feedback button and sending feedback are off | 77+ |
| `edge.signin-off` | `BrowserSignin = 0` | Signing in to the browser is not allowed (commented out in the script) | 77+ |
| `edge.password-manager-off` | `PasswordManagerEnabled = 0` | The password manager does not offer to save passwords; level risky: users tend to reuse passwords without it (commented out in the script) | 77+ |
| `edge.autofill-cards-off` | `AutofillCreditCardEnabled = 0` | Payment cards are not saved or filled in (commented out in the script) | 77+ |

`BackgroundModeEnabled = 0` and `HideFirstRunExperience = 1` of the script are already set by `edge.baseline`.

### AI policies (customer list of 28.09.2026)

On by default. Most Edge AI policies say "Applies to a profile that is signed in with a Microsoft account: No":
a profile signed in with a personal Microsoft account escapes them. That is why `edge.signin-off`
(`BrowserSignin = 0`) and `edge.sidebar-off` are on by default since 28.09.2026 as well.

| Rule | Value | Effect | Edge |
|---|---|---|---|
| `edge.genai-local-model-off` | `GenAILocalFoundationalModelSettings = 1` | The local GenAI model is not downloaded, a downloaded one is deleted; applies to personal-account profiles too | 132+ |
| `edge.builtin-ai-apis-off` | `BuiltInAIAPIsEnabled = 0` | Sites cannot call the LanguageModel, Summarizer, Writer, Rewriter APIs | 138+ |
| `edge.history-ai-search-off` | `EdgeHistoryAISearchEnabled = 0` | History search by exact match only | 138+ |
| `edge.ai-themes-off` | `AIGenThemesEnabled = 0` | No DALL-E themes | 122+ |
| `edge.text-prediction-off` | `TextPredictionEnabled = 0` | No cloud text predictions in text fields (nearby, not on the list) | 104+ |
| `edge.tab-services-off` | `TabServicesEnabled = 0` | Tab data is not sent for grouping (nearby) | 113+ |
| `edge.autofill-ml-off` | `EdgeAutofillMlEnabled = 0` | No cloud machine learning for autofill (nearby) | 132+ |
| `edge.copilot-address-bar-off` | `CopilotAddressBarSuggestionsEnabled = 0` | No Copilot suggestions in the address bar (nearby) | 149+ |
| `edge.ntp-copilot-off` | `NewTabPageBingChatEnabled = 0` | No Copilot entry points on the new tab page (nearby; effect on unsigned profiles not described) | 117+ |
| `edge.copilot-cowork-off` | `CopilotCoworkToolActionsEnabled = 0` | Cowork does not act for the user (nearby) | 152+ |
| `edge.browsing-with-copilot-off` | `AllowBrowsingWithCopilot = 0` | Agentic browsing off (nearby; the feature needs a Microsoft 365 Copilot licence) | 148+ |
| `edge.copilot-page-context-off` | `CopilotPageContext = 0` | Copilot cannot read pages; Entra ID profiles only | 124+ |
| `edge.entra-copilot-page-context-off` | `EdgeEntraCopilotPageContext = 0` | Copilot with data protection cannot read pages, history, transcripts; Entra ID profiles only | 130+ |
| `edge.m365-copilot-icon-off` | `Microsoft365CopilotChatIconEnabled = 0` | No Microsoft 365 Copilot Chat icon; Entra ID profiles only | 139+ |
| `edge.compose-inline-off` | `ComposeInlineEnabled = 0` | No Copilot rewrite; Entra ID accounts only | 115+ |
| `edge.copilot-search-history-off` | `ShareBrowsingHistoryWithCopilotSearchAllowed = 0` | History not shared with Microsoft 365 Copilot Search; Entra ID with a licence only | 143+ |
| `edge.visual-search-off` (off by default) | `VisualSearchEnabled = 0` | No Bing visual search | 95+ |
| `edge.search-in-sidebar-off` (off by default) | `SearchInSidebarEnabled = 2` | Search results not in the sidebar | 110+ |

The Entra ID policies have no effect with local accounts and browser sign-in blocked; they are generated because
the customer's list names them. `CopilotCDPPageContext` (obsolete after Edge 132) and `DevToolsGenAiSettings` (a
Chrome policy, not an Edge one) of the list are not generated. No documented policy exists for the Copilot button
on unsigned profiles since Edge 141, for Copilot Mode and for "Explain this error" in DevTools: check `edge://policy`
and the toolbar in a VM.

## Google Chrome

Key: `HKLM\SOFTWARE\Policies\Google\Chrome`, all values REG_DWORD.

| Rule | Value | Effect | Chrome |
|---|---|---|---|
| `chrome.metrics-off` | `MetricsReportingEnabled = 0` | No usage statistics or crash reports to Google | 8+ |
| `chrome.variations` | `ChromeVariations = 1` (parameter: 1 or 2) | Only critical security and stability variations are applied; 2 disables all, which Google does not recommend because it can delay critical security fixes | 83+ |
| `chrome.sync` | `SyncDisabled = 1` (parameter: 1 or 0) | Sync with the Google account is disabled; 0, the value of the script, leaves the choice to the user | 8+ |
| `chrome.background-off` | `BackgroundModeEnabled = 0` | Chrome does not keep running after its last window is closed | 19+ |
| `chrome.genai-off` | `GenAiDefaultSettings = 2` | Generative AI features are not allowed by default | 130+ |
| `chrome.genai-local-model-off` | `GenAILocalFoundationalModelSettings = 1` | The local generative AI model (gigabytes) is not downloaded | 124+ |
| `chrome.devtools-genai-off` | `DevToolsGenAiSettings = 2` | No generative AI in DevTools | 125+ |
| `chrome.lens-overlay-off` | `LensOverlaySettings = 1` | Google Lens overlay is not allowed; deprecated from Chrome 147 | 126+ |
| `chrome.translate-off` | `TranslateEnabled = 0` | No page translation offers | 12+ |
| `chrome.signin-off` | `BrowserSignin = 0` | Signing in to the browser is not allowed | 70+ |
| `chrome.search-suggest-off` | `SearchSuggestEnabled = 0` | No search suggestions in the address bar | 8+ |
| `chrome.cast-private-only` | `MediaRouterCastAllowAllIPs = 0` | Google Cast connects only to devices on private addresses | 67+ |
| `chrome.promotions-off` | `PromotionsEnabled = 0` | No promotional tabs and content; replaces the deprecated `PromotionalTabsEnabled` | 128+ |
| `chrome.password-manager-off` | `PasswordManagerEnabled = 0` | The password manager does not offer to save passwords; level risky (commented out in the script) | 8+ |
| `chrome.autofill-address-off` | `AutofillAddressEnabled = 0` | Addresses are not saved or filled in (commented out in the script) | 69+ |
| `chrome.autofill-cards-off` | `AutofillCreditCardEnabled = 0` | Payment cards are not saved or filled in (commented out in the script) | 63+ |
| `chrome.builtin-dns-off` | `BuiltInDnsClientEnabled = 0` | Names are resolved by the Windows DNS client, so the organisation's DNS settings and hosts file apply (commented out in the script) | 25+ |

## Brave

Key: `HKLM\SOFTWARE\Policies\BraveSoftware\Brave`, all values REG_DWORD. Brave also reads Chromium policies
such as `TranslateEnabled` from this key.

| Rule | Value | Effect |
|---|---|---|
| `brave.rewards-off` | `BraveRewardsDisabled = 1` | Brave Rewards unavailable |
| `brave.wallet-off` | `BraveWalletDisabled = 1` | Brave Wallet unavailable |
| `brave.vpn-off` | `BraveVPNDisabled = 1` | Brave VPN unavailable |
| `brave.ai-chat-off` | `BraveAIChatEnabled = 0` | The Leo AI assistant (AI Chat) unavailable |
| `brave.stats-ping-off` | `BraveStatsPingEnabled = 0` | No daily usage ping |
| `brave.p3a-off` | `BraveP3AEnabled = 0` | No privacy-preserving product analytics (P3A) |
| `brave.news-off` | `BraveNewsDisabled = 1` | Brave News unavailable |
| `brave.talk-off` | `BraveTalkDisabled = 1` | Brave Talk unavailable |
| `brave.playlist-off` | `BravePlaylistEnabled = 0` | Playlist unavailable |
| `brave.speedreader-off` | `BraveSpeedreaderEnabled = 0` | Speedreader unavailable |
| `brave.wayback-off` | `BraveWaybackMachineEnabled = 0` | No Wayback Machine prompts |
| `brave.web-discovery-off` | `BraveWebDiscoveryEnabled = 0` | Web Discovery (contribution to the Brave Search index) off |
| `brave.translate-off` | `TranslateEnabled = 0` | No page translation offers |
| `brave.tor-off` | `TorDisabled = 1` | Private windows with Tor unavailable; level recommended: Tor traffic bypasses the organisation's filtering |

## Corrections to the scripts of issue #1

Lines of the scripts that are not turned into rules, or are turned into rules with another name or value:

| Script line | Finding | In WinKickOff |
|---|---|---|
| Edge `MetricsReportingEnabled = 0` | Obsolete policy | Replaced by `DiagnosticData = 0` |
| Edge `SendSiteInfoToImproveServices = 0` | Obsolete policy | Replaced by `DiagnosticData = 0` |
| Edge `DiagnosticDataEnabled = 0` | No such policy | `DiagnosticData = 0` |
| Edge `EdgeCopilotEnabled = 0` | Android and iOS only | Not generated; on Windows `HubsSidebarEnabled` hides the Copilot button before Edge 141 |
| Edge `CopilotPageContext = 0` | Applies only to Microsoft Entra ID profiles | Not generated: no effect in a workgroup |
| Edge `Microsoft365CopilotChatIconEnabled = 0` | Applies only to Microsoft Entra ID profiles | Not generated: no effect in a workgroup |
| Edge `EdgeCollectionsEnabled = 0` | Obsolete: Collections removed in Edge 153 | Not generated |
| Edge `ShoppingAssistantEnabled = 0` | No such policy | `EdgeShoppingAssistantEnabled = 0` |
| Edge `RewardsEnabled = 0` | No such policy | `ShowMicrosoftRewards = 0` |
| Edge `PrintPDFAsImageEnabled = 0` | No such policy; the closest, `PrintPdfAsImageDefault`, is off by default | Not generated |
| Edge `BackgroundModeEnabled = 0`, `HideFirstRunExperience = 1` | Already in `edge.baseline` | Not duplicated |
| Chrome `ReportingEnabled = 0`, `UserMetricsReportingEnabled = 0` | No such policies | Covered by `MetricsReportingEnabled = 0` |
| Chrome `ChromeVariationsEnabled = 0` | No such policy | `ChromeVariations`, default 1 |
| Chrome `SyncDisabled = 0` | Leaves the choice to the user, which is the behaviour without the policy | Parameter of `chrome.sync`, default 1 as for Edge |
| Chrome `LensOverlaySettings = 0` | 0 means "Allow" | `LensOverlaySettings = 1` |
| Chrome `LensSettings = 0` | No such policy | Not generated |
| Chrome `AutofillPaymentCardBenefitsEnabled = 0` | No such policy | Not generated |
| Chrome `PromotionalTabsEnabled = 0` | Deprecated | `PromotionsEnabled = 0` |
| Chrome `NTPShortcutsEnabled = 0` | No such policy (`NTPShortcuts` is a list of shortcuts, not a switch) | Not generated |
| Brave `BraveP3ADisabled = 1` | No such policy | `BraveP3AEnabled = 0` |
| Brave `BraveStatsPingDisabled = 1` | No such policy | Covered by `BraveStatsPingEnabled = 0` |
| Brave `BraveLeoEnabled = 0` | No such policy; Leo is controlled by AI Chat | Covered by `BraveAIChatEnabled = 0` |

## Verification and rollback

- Verification: `edge://policy`, `chrome://policy` or `brave://policy` lists every applied policy with its
  source "Platform" and status; in the registry, `reg query` of the key above. WinKickOff shows the exact
  command for each rule and can check the selection on a running PC («Этот ПК» (This PC)).
- Rollback: delete the value from the policy key; the browser returns to its default behaviour and the
  setting becomes editable again after a restart of the browser.

## Sources

- Microsoft Edge Browser Policy Documentation, learn.microsoft.com/deployedge/microsoft-edge-browser-policies/<policy>.
- Chrome Enterprise policy list (policy_templates_en-US.json of chromeenterprise.google) and
  `components/policy/resources/templates/policies.yaml` of Chromium.
- Brave policy definitions: `components/policy/resources/templates/policy_definitions/BraveSoftware` of brave-core.
