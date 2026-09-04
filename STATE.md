# STATE — GHLchat-Chatbot
Last updated: 2026-09-03 by Coordinator

## Status
Owner: Referral Report (Clinical lane; Bedrock BAA path). Engine built and offline-validated 2026-07-22 (35/35 selftests; live Bedrock smoke passed). Nothing has touched the live GHL account. Gated on Augustine's approval (Chatbot_Integration_Approval.docx). No activity since 07-22.

## Done
- 2026-07-22 Engine offline-validated
- 2026-09-03 STATE.md seeded from START_HERE.md and engine\BUILD_STATUS.md (Coordinator)

## In progress
- Blocked on approval: bot token (A1), inbound path (A2), hosting (A3), calendar/stage ids, dummy contact. Approval is external communication → queues for Harry (Part 3 #2) if it needs a send.
- After approval: inbound receiver, booking sub-flow, supervised pilot — Referral Report

## Broken / not mine
- Human-standdown / thread parsing written against documented payload shape; unverified against a real payload

## Decisions
- 2026-07-21 GHL confirmed BAA-covered
- 2026-07-22 v1 = one bot for web bubble + new-lead SMS; no-show/win-back later
- 2026-09-03 Chatbot deployment owned by Referral Report — Coordinator at standup
- 2026-09-03 RULES.md adopted at estate root; supersedes GOLDEN_RULES/GOVERNANCE where they conflict — Harry standup
- 2026-09-03 Spend threshold $200 cumulative/month, all agents; pre-authorized list confirmed as written — Harry
- 2026-09-03 Auditor (Compliance Advisor) is records-only; nothing operational — Harry
- 2026-09-03 Stop-Manager ignored, not staffed — Harry
- 2026-09-03 No agent-initiated migration/restructure/cleanup — RULES.md Part 2

## Change requests
- (none)

## DO NOT TOUCH
- Bedrock only; conversation logs are PHI — never paste/commit/email
- ghl_client uses its own token — never point at helper_config.json
- Sends stay simulated unless allow_real_sends AND allowlist
