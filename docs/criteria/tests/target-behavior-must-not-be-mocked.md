---
name: target-behavior-must-not-be-mocked
when: Always.
---

# Target Behavior Must Not Be Mocked

Tests must verify the actual behavior of the system under test rather than mocking or stubbing it. This ensures that the tests accurately reflect how the system will behave in production. Mocking is only allowed for external dependencies that are not part of the system under test, and even then, it should be used judiciously to avoid hiding important interactions.

## Illustrations

### Mocking The System Under Test

```markdown
plan.md
# Verify that `route_event` dispatches MCP events to the correct handler
- [ ] Test that `event.kind == "agent.start"` lands in the start handler
...
```

**Bad - the routing logic itself is mocked.** The test replaces
`route_event` with a stub, so it asserts the stub was called rather than
that real routing works.

```python
def test_route_event_dispatches(mocker):
    route = mocker.patch("cao.events.route_event")

    handle_incoming({"kind": "agent.start"})

    route.assert_called_once_with({"kind": "agent.start"})
```

**Good:** The test exercises the real routing function and checks the
handler saw the event.

```python
def test_agent_start_lands_in_start_handler():
    handler = RecordingHandler()
    router = EventRouter(handlers={"agent.start": handler})

    router.route({"kind": "agent.start", "agent_id": "a1"})

    assert handler.received == [{"kind": "agent.start", "agent_id": "a1"}]
```

### Mocking Only The External Boundary

```markdown
plan.md
# The reviewer talks to an external Claude API
- [ ] Test that reviewer publishes the result it gets back
...
```

**Good:** Internal collaborators run for real; only the third-party API
client is faked, and through its defined interface.

```python
class FakeClaudeClient:
    def chat(self, messages):
        return ChatResponse(text="ok")

def test_reviewer_publishes_result():
    reviewer = Reviewer(client=FakeClaudeClient(), store=InMemoryReviewStore())

    reviewer.review(ChangeSet(diff="..."))

    assert reviewer.store.latest().text == "ok"
```
