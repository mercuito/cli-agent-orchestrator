# Fix CAO Agent Directory Routing

## Problem

`cao-server --agents-dir <path>` advertises that it overrides the server's agent
directory, but live verification showed new dashboard-created agents were still
written under `~/.aws/cli-agent-orchestrator/agents`.

The root cause appears to be split ownership of "agent directory" state:

- `src/cli_agent_orchestrator/constants.py` defines `KIRO_AGENTS_DIR` from
  `CAO_AGENTS_DIR`.
- `src/cli_agent_orchestrator/agent.py` defines CAO durable agent storage as
  `AGENTS_ROOT = CAO_HOME_DIR / "agents"`.
- `src/cli_agent_orchestrator/api/main.py` imports `AGENTS_ROOT` by value and
  calls `write_agent`, `load_agent`, and `patch_agent_config` without an
  explicit `agents_root`.
- `api.main.main()` updates `os.environ["CAO_AGENTS_DIR"]` and
  `constants.KIRO_AGENTS_DIR`, but it does not update the CAO durable
  `agent.AGENTS_ROOT` or the already-imported `api.main.AGENTS_ROOT`.

The current tests mostly monkeypatch both constants directly, so they verify
CRUD behavior under patched module globals but not the CLI/env boundary.

## Desired Behavior

When `cao-server --agents-dir /some/root` is used, all dashboard and API agent
CRUD operations must read, write, update, list, and delete durable CAO agents
under `/some/root`.

If `CAO_AGENTS_DIR=/some/root` is set before server startup, the same behavior
should hold. If both are present, the explicit CLI flag should win for that
process.

This plan is about the CAO durable agent root, not provider-specific legacy Kiro
agent storage.

## Design Direction

Prefer a single authoritative CAO agent root resolver owned by
`cli_agent_orchestrator.agent`.

Likely implementation shape:

1. Add an authoritative constant for the environment key, e.g.
   `CAO_AGENTS_DIR_ENV = "CAO_AGENTS_DIR"`.
2. Add a boundary function such as `configure_agents_root(path: Path) -> None`
   in `agent.py` that updates the module's durable `AGENTS_ROOT`.
3. Add a resolver such as `default_agents_root()` or a module-level
   initialization that reads `CAO_AGENTS_DIR` once at the application boundary.
4. Update API code to stop importing `AGENTS_ROOT` by value for mutable runtime
   storage decisions. Use `agent.AGENTS_ROOT`, `default_agents_root()`, or pass
   an explicit root into `load_agent`, `write_agent`, `patch_agent_config`, and
   delete paths.
5. Update CLI/server startup so `--agents-dir` calls the CAO root configuration
   function and only touches Kiro-specific state if that is still needed for a
   separate provider path.

Avoid spreading new direct `os.environ` reads into service or helper code. Read
global runtime state at process startup or through one owned resolver.

## Test Plan

Add tests before implementation where practical:

1. Unit/API boundary test for startup:
   - Given `main()` receives `--agents-dir <tmp>/agents`
   - When it configures the server
   - Then the CAO durable agent root used by create/update/delete is that path,
     not the default home path.

2. API behavior test through the owner surface:
   - Given the API is configured with an isolated `agents_root`
   - When `POST /agents` creates an agent
   - Then `<agents_root>/<id>/agent.toml` and `prompt.md` exist.
   - When `PUT /agents/{id}` saves `model` and `reasoning_effort`
   - Then the same `agent.toml` contains those keys.
   - When `DELETE /agents/{id}?confirm=true` succeeds
   - Then the directory under the isolated root is removed.

3. Regression test for `CAO_AGENTS_DIR`:
   - Given the environment is set before importing/configuring the server
   - When the agent root is resolved/configured
   - Then it uses that value.

4. Existing test cleanup:
   - Replace tests that monkeypatch multiple module-level `AGENTS_ROOT`
     bindings with the new authoritative configuration seam where possible.
   - Keep filesystem artifacts under `tmp_path`.

5. Verification after implementation:
   - Focused API tests around agent CRUD and server main.
   - Full relevant Python checks: `uv run pytest test/api/test_agent_routes.py
     test/api/test_api_endpoints.py test/test_agent.py`.
   - Formatting/type checks if production code changes: `uv run black --check
     src test`, `uv run isort --check-only src test`, and `uv run mypy src`.
   - A live smoke with `cao-server --agents-dir <tmp>` creating and saving a
     throwaway dashboard/API agent, then reading `<tmp>/<id>/agent.toml`.

## Criteria Catalog

Criteria catalog was reviewed during planning with `uv run python
scripts/catalog_criteria.py`.

Likely implementation criteria to consult during the actual diff:

- `docs/criteria/implementation/authoritative-sources-are-referenced-not-copied.md`
- `docs/criteria/implementation/no-global-state-reads.md`
- `docs/criteria/implementation/minimal-cohesive-changes.md`
- `docs/criteria/implementation/no-unnecessary-duplication.md`
- `docs/criteria/implementation/readable-and-explicit.md`
- `docs/criteria/implementation/system-code-locality.md`

Likely test criteria:

- `docs/criteria/tests/all-system-behaviors-are-verified-by-tests.md`
- `docs/criteria/tests/given-when-then-test-structure.md`
- `docs/criteria/tests/target-behavior-must-not-be-mocked.md`
- `docs/criteria/tests/test-artifact-containment.md`
- `docs/criteria/tests/test-through-owner-surfaces.md`

After implementation, evaluate the pending changes against the criteria catalog.
No criteria applicable to the completed diff may be violated.

## Open Questions

- Should `CAO_AGENTS_DIR` continue to affect `KIRO_AGENTS_DIR`, or should that
  legacy/provider-specific behavior be split into a separate env key?
- Should the durable default remain `~/.aws/cli-agent-orchestrator/agents`, or
  should it also become configurable through a more explicit CAO-specific name
  while keeping `CAO_AGENTS_DIR` as a compatibility alias?
- Do CLI commands under `src/cli_agent_orchestrator/cli/commands/agent.py` need
  the same runtime override behavior now, or only the server entrypoint?

## Implementation Result

Implemented on 2026-05-17:

- `cli_agent_orchestrator.agent` now owns the authoritative durable CAO agent
  root, honors `CAO_AGENTS_DIR` at import, and exposes
  `configure_agents_root()` for startup-time overrides.
- `cao-server --agents-dir <root>` now configures the CAO durable agent root and
  keeps the legacy `KIRO_AGENTS_DIR` compatibility assignment.
- API and durable agent CLI code now read the live root from
  `cli_agent_orchestrator.agent` instead of keeping copied `AGENTS_ROOT`
  bindings for filesystem decisions.
- API CRUD regression coverage verifies model and reasoning effort updates are
  persisted to the isolated configured root.

Verification completed:

- `uv run pytest test/api/test_agent_routes.py test/api/test_api_endpoints.py test/test_agent.py test/cli/commands/test_agent.py`
- `uv run black --check src test`
- `uv run isort --check-only src test`
- `uv run mypy src`
- `git diff --check`
- Live server smoke with `cao-server --agents-dir <tmp>` verified API
  create/update wrote `model` and `reasoning_effort` to `<tmp>/<id>/agent.toml`
  and did not create the probe under the default CAO agents directory.
