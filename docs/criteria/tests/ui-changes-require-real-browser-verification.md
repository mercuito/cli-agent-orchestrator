---
name: ui-changes-require-real-browser-verification
when: Frontend or dashboard changes alter user-visible UI behavior, navigation, actions, runtime links, auth-sensitive calls, or built static assets.
---

# UI Changes Require Real Browser Verification

UI changes must be verified through the real browser surface that users will
exercise, not only through component tests or mocked API calls. Automated tests
should still cover the focused behavior, but any user-visible workflow changed
by the diff needs at least one browser verification pass against the served app
or the built artifact that will actually be used.

When the UI is served differently in development and production, verification
must use the relevant served target. For dashboard changes that are consumed
through the backend static bundle, rebuild the frontend and verify the
backend-served dashboard after refreshing the browser. For workflows that
depend on host, auth, signed tokens, websocket permissions, cookies, or remote
access, verify from the same class of URL users will use, such as a remote or
Tailscale URL rather than only loopback.

The verification note must name what was clicked or exercised, the browser or
target URL class used, and the observed result. If a real-browser check is
impractical, the completion report must explain why and name the remaining
risk.

## Illustrations

### Mocked Click Without The Served App

```markdown
plan.md
# Move terminal opening from session rows to agent rows
- [ ] Clicking Open Terminal on a running agent opens the terminal overlay
```

**Bad - the UI handler is tested but the deployed path is not.** The test
mocks the API wrapper, so it proves only that the click calls a function. It
does not prove the browser sends the auth token required by the real endpoint,
that the built bundle was refreshed, or that the websocket can open from the
remote dashboard host.

```tsx
it("opens a terminal", async () => {
  api.getAgentRuntimeTerminal.mockResolvedValue({
    terminal: { id: "term-1", provider: "codex", agent_id: "agent-1" },
    terminal_token: "token-1",
  })

  fireEvent.click(screen.getByRole("button", { name: /open terminal/i }))

  expect(TerminalView).toHaveBeenCalled()
})
```

**Good:** The focused test still exists, and final verification also runs the
served dashboard in a browser. The verifier reloads the backend-served page,
clicks `Open Terminal` for a running agent, and confirms the terminal overlay
opens without the auth error seen on the real remote host.

```markdown
Verification:
- `npm test -- src/test/agent-panel-deeplink.test.tsx` passed.
- `npm run build` passed.
- Safari, backend-served Tailscale dashboard: reloaded the Agents tab, clicked
  Open Terminal for `discovery_partner`, and observed terminal `1075eea7`
  open without a 403.
```

### Development Server Is Not Enough For Static Bundles

```markdown
plan.md
# Update the dashboard configuration form
- [ ] Model and reasoning controls save from the dashboard
```

**Bad:** The verifier checks only the Vite dev server, while the user opens the
backend-served static dashboard. The change can pass locally but still be absent
from the bundle the user loads.

```markdown
Verification:
- Chrome at `http://localhost:5173`: selected a model and saw the form update.
```

**Good:** The verification covers the artifact and host class that users
actually use.

```markdown
Verification:
- `npm run build` updated `src/cli_agent_orchestrator/web_ui`.
- Safari at the backend-served dashboard URL: refreshed the page, changed model
  and reasoning controls, saved, reloaded, and confirmed the values persisted.
```
