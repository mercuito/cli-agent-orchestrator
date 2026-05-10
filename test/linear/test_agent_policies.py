"""Tests for Linear agent-presence policy evaluation."""

from __future__ import annotations

from cli_agent_orchestrator.linear.agent_policies import (
    LinearAgentPolicy,
    LinearAgentPolicyEvaluator,
    LinearAgentPolicyRegistry,
    LinearIssueFacts,
    LinearPolicyContext,
    LinearPolicyDecision,
    LinearPolicyFactError,
    LinearPolicyRequest,
    LinearPolicyValidator,
    check_discovery_partner_can_receive_delegate,
)


def _request(**overrides):
    values = {
        "agent_id": "discovery_partner",
        "direction": "incoming",
        "action": "delegate",
        "origin": "webhook",
        "issue_id": "CAO-69",
    }
    values.update(overrides)
    return LinearPolicyRequest(**values)


def test_discovery_partner_allows_unmarked_front_door_issue():
    context = LinearPolicyContext(
        request=_request(),
        issue=LinearIssueFacts(
            id="issue-1",
            identifier="CAO-69",
            title="Loose idea that needs shaping",
            state_name="Todo",
            state_type="unstarted",
            labels=(),
        ),
    )

    decision = check_discovery_partner_can_receive_delegate(context)

    assert decision.allowed is True


def test_discovery_partner_denies_downstream_labels():
    context = LinearPolicyContext(
        request=_request(),
        issue=LinearIssueFacts(
            id="issue-1",
            identifier="CAO-69",
            title="Implement the thing",
            state_name="Todo",
            state_type="unstarted",
            labels=("implementation",),
        ),
    )

    decision = check_discovery_partner_can_receive_delegate(context)

    assert decision.allowed is False
    assert "downstream execution labels" in decision.reason
    assert decision.diagnostics == {"matched_labels": ("implementation",)}


def test_discovery_partner_denies_handoff_markers():
    context = LinearPolicyContext(
        request=_request(),
        issue=LinearIssueFacts(
            id="issue-1",
            identifier="CAO-69",
            title="Build bounded task",
            description="## Coding Implementation Plan\n\nDo the task.",
            state_name="Todo",
            state_type="unstarted",
        ),
    )

    decision = check_discovery_partner_can_receive_delegate(context)

    assert decision.allowed is False
    assert "handoffs" in decision.reason
    assert decision.diagnostics == {"matched_marker": "Coding Implementation Plan"}


def test_evaluator_hydrates_required_facts_before_validator_runs():
    calls = []

    def check(context):
        calls.append(context.require_issue().identifier)
        return LinearPolicyDecision.allow()

    validator = LinearPolicyValidator(
        name="needs_issue",
        required_facts=frozenset({"issue"}),
        check=check,
    )
    evaluator = LinearAgentPolicyEvaluator(
        registry=LinearAgentPolicyRegistry(
            (
                LinearAgentPolicy(
                    agent_id="discovery_partner",
                    direction="incoming",
                    action="delegate",
                    validators=(validator,),
                ),
            )
        ),
        load_facts=lambda request, required: LinearPolicyContext(
            request=request,
            issue=LinearIssueFacts(id="issue-1", identifier="CAO-69"),
        ),
    )

    decision = evaluator.evaluate(_request())

    assert decision.allowed is True
    assert calls == ["CAO-69"]


def test_evaluator_turns_missing_required_facts_into_denial():
    validator = LinearPolicyValidator(
        name="needs_issue",
        required_facts=frozenset({"issue"}),
        check=lambda context: LinearPolicyDecision.allow(),
    )

    def missing_issue(request, required):
        raise LinearPolicyFactError("issue", "policy request has no issue id")

    evaluator = LinearAgentPolicyEvaluator(
        registry=LinearAgentPolicyRegistry(
            (
                LinearAgentPolicy(
                    agent_id="discovery_partner",
                    direction="incoming",
                    action="delegate",
                    validators=(validator,),
                ),
            )
        ),
        load_facts=missing_issue,
    )

    decision = evaluator.evaluate(_request(issue_id=None))

    assert decision.allowed is False
    assert decision.policy_name == "linear_policy_fact_hydration"
    assert decision.diagnostics == {
        "missing_fact": "issue",
        "detail": "policy request has no issue id",
    }
