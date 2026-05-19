# Review Findings Reference

This file preserves the signal from the old monolithic review-hardening log.
The findings were reviewed after ToolService consolidation. They are reference
material for the child plans, not a second source of requirements.

| Review | Disposition | Carried into |
| --- | --- | --- |
| R01 | Still relevant: team membership, Linear role-only loading, provider views, provider-owned role schemas. | 01, 02, 03 |
| R02 | No findings. | None |
| R03 | Still relevant: runtime material/freshness and team-aware validation/editing. | 01, 04 |
| R04 | Still relevant: direct/custom `mcp_servers` are tool access. | 01, 04 |
| R05 | Still relevant: diagnostics/preflight must use effective MCP servers. | 04 |
| R06 | Still relevant: managed `cao-mcp-server` is separate from role-owned `mcp_servers`; Copilot runtime must align. | 04 |
| R07 | Still relevant: role provider access expands to agent-scoped requests; Linear identity remains agent-owned. | 01, 02 |
| R08 | Still relevant: default `member` role and CLI inspection semantics. | 01, 04 |
| R09 | Still relevant: backend-owned built-in CAO tool descriptors. | 03 |
| R10 | Still relevant: provider identity validation and prompt/skill visibility. | 02, 04 |
| R11 | Partly satisfied by ToolService fail-closed behavior; still relevant for team-role resolution failures and nested provider MCP bypasses. | 01, 04 |
| R12 | Refined: provider-backed inbox read/reply is scoped to the inbox item and recipient/provider identity, not broad provider-mediated grants. Raw `agent.toml` inactive UI still relevant. | 02, 03 |
| R13 | Still relevant: provider-native runtime capabilities stay separate; Vite proxy must support new APIs. | 01, 03 |
| R14 | Narrowed: authorize provider-backed notification body delivery before terminal delivery; broad transcript redaction is out of scope. | 02 |
| R15 | Narrowed: provider-backed inbox operations use scoped notification/thread authorization; no separate Linear tool grant unless broader provider work is performed. | 02 |
| R16 | Mostly deferred: monitor/webhook redesign is out of scope, but touched delivery paths must honor effective authorization. | 02, 04 |
| R17 | Still relevant: team persistence/API updates must preserve roles and assignments. | 01, 03 |
| R18 | Mostly deferred: broad timeline redaction is out of scope unless this work changes those surfaces. | 04 |
| R19 | Narrowed: stored inbox reads should not bypass scoped inbox authorization; broad monitoring/log redaction is out of scope. | 02, 04 |
| R20 | Still relevant: baton guidance should respect visible role tools. | 04 |
| R21 | Still relevant: provider grants must match team workspace setup; Linear guardrails remain provider-owned. | 02 |
| R22 | Still relevant: `terminate` same-team constraint and generated guidance. | 04 |
| R23 | Narrowed: raw transcripts/logs are operator/debug surfaces; label them, do not redesign redaction here. | 04 |
| R24 | Partly deferred: timeline read-subject redaction is out of scope; provider-global MCP reconciliation remains relevant. | 04 |
| R25 | Narrowed: live terminal streaming/attach are transcript surfaces; Linear external URL infrastructure writes are out of scope unless touched. | 04 |
| R26 | Mostly deferred: runtime notification event redaction only applies if this work changes provider-backed notification payloads. | 02, 04 |
| R27 | Refined: live revocation is handled as stale runtime configuration; workspace-provider role schema namespace remains relevant. | 03, 04 |
