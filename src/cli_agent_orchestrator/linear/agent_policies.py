"""Linear agent-presence policy evaluation.

Policies here answer one boring question: can this CAO-backed Linear agent
participate in this Linear action?  The evaluator is shared by webhook intake
and provider-tool hooks; adapters decide what to do with a denial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, Mapping, Optional

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.workspace_provider import LinearPresence

LinearPolicyDirection = Literal["incoming", "outgoing"]
LinearPolicyAction = Literal[
    "delegate",
    "mention",
    "create_issue",
    "create_comment",
    "change_status",
]
LinearPolicyOrigin = Literal["tool_call", "webhook", "monitor"]
LinearPolicyActorKind = Literal["human", "agent", "linear_app", "unknown"]
LinearPolicyFact = Literal["issue", "actor", "target_agent"]

DOWNSTREAM_DISCOVERY_LABELS = frozenset(
    {
        "implementation",
        "implementer",
        "review",
        "reviewer",
        "test",
        "testing",
        "qa",
        "release",
        "refactor",
    }
)
DOWNSTREAM_DISCOVERY_STATE_TYPES = frozenset({"started", "completed"})
DOWNSTREAM_DISCOVERY_STATE_NAMES = frozenset(
    {
        "in progress",
        "in review",
        "ready for review",
        "done",
        "canceled",
        "cancelled",
    }
)
DOWNSTREAM_DISCOVERY_MARKERS = frozenset(
    {
        "Feature Task Handoff",
        "Coding Implementation Plan",
        "Coding Code Contract",
        "Coding Test Contract",
        "Code Contract Defence",
        "Test Contract Defence",
        "Behavioral Contract Defence",
    }
)


class LinearPolicyFactError(ValueError):
    """Raised when a requested policy fact cannot be loaded."""

    def __init__(self, fact: str, detail: str) -> None:
        self.fact = fact
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class LinearIssueFacts:
    """The bounded issue facts policy validators may inspect."""

    id: str
    identifier: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    state_name: Optional[str] = None
    state_type: Optional[str] = None
    labels: tuple[str, ...] = ()
    team_key: Optional[str] = None
    team_name: Optional[str] = None
    project_name: Optional[str] = None
    parent_identifier: Optional[str] = None
    delegate_name: Optional[str] = None
    assignee_name: Optional[str] = None

    def has_any_label(self, labels: Iterable[str]) -> bool:
        wanted = {_normalized_text(label) for label in labels}
        return any(_normalized_text(label) in wanted for label in self.labels)

    def matched_labels(self, labels: Iterable[str]) -> tuple[str, ...]:
        wanted = {_normalized_text(label) for label in labels}
        return tuple(label for label in self.labels if _normalized_text(label) in wanted)

    def contains_any_marker(self, markers: Iterable[str]) -> Optional[str]:
        haystack = "\n".join(part for part in (self.title or "", self.description or "") if part)
        haystack_lower = haystack.lower()
        for marker in markers:
            if marker.lower() in haystack_lower:
                return marker
        return None


@dataclass(frozen=True)
class LinearPolicyRequest:
    """A normalized request to evaluate one Linear agent-presence action."""

    agent_id: str
    direction: LinearPolicyDirection
    action: LinearPolicyAction
    origin: LinearPolicyOrigin
    actor_id: Optional[str] = None
    actor_kind: LinearPolicyActorKind = "unknown"
    issue_id: Optional[str] = None
    target_agent_id: Optional[str] = None


@dataclass(frozen=True)
class LinearPolicyDecision:
    """Allow or deny result from Linear agent policy evaluation."""

    allowed: bool
    reason: str = ""
    diagnostics: Mapping[str, Any] | None = None
    policy_name: Optional[str] = None

    @classmethod
    def allow(cls) -> "LinearPolicyDecision":
        return cls(allowed=True)

    @classmethod
    def deny(
        cls,
        reason: str,
        *,
        diagnostics: Mapping[str, Any] | None = None,
        policy_name: Optional[str] = None,
    ) -> "LinearPolicyDecision":
        return cls(
            allowed=False,
            reason=reason.strip(),
            diagnostics=dict(diagnostics or {}),
            policy_name=policy_name,
        )


@dataclass(frozen=True)
class LinearPolicyContext:
    """Facts available to one policy validator."""

    request: LinearPolicyRequest
    issue: Optional[LinearIssueFacts] = None

    def require_issue(self) -> LinearIssueFacts:
        if self.issue is None:
            raise LinearPolicyFactError("issue", "Linear policy requires issue facts")
        return self.issue


LinearPolicyCheck = Callable[[LinearPolicyContext], LinearPolicyDecision]


@dataclass(frozen=True)
class LinearPolicyValidator:
    """Named validator plus the facts it requires."""

    name: str
    required_facts: frozenset[LinearPolicyFact]
    check: LinearPolicyCheck


@dataclass(frozen=True)
class LinearAgentPolicy:
    """Validators for one agent, direction, and action."""

    agent_id: str
    direction: LinearPolicyDirection
    action: LinearPolicyAction
    validators: tuple[LinearPolicyValidator, ...]


class LinearAgentPolicyRegistry:
    """Lookup policies by agent id, direction, and action."""

    def __init__(self, policies: Iterable[LinearAgentPolicy]) -> None:
        self._policies = tuple(policies)

    def match(self, request: LinearPolicyRequest) -> tuple[LinearAgentPolicy, ...]:
        return tuple(
            policy
            for policy in self._policies
            if policy.agent_id == request.agent_id
            and policy.direction == request.direction
            and policy.action == request.action
        )


LinearPolicyFactLoader = Callable[
    [LinearPolicyRequest, frozenset[LinearPolicyFact]], LinearPolicyContext
]


@dataclass(frozen=True)
class LinearAgentPolicyEvaluator:
    """Evaluate matching Linear agent policies with declared fact hydration."""

    registry: LinearAgentPolicyRegistry
    load_facts: LinearPolicyFactLoader

    def evaluate(self, request: LinearPolicyRequest) -> LinearPolicyDecision:
        policies = self.registry.match(request)
        if not policies:
            return LinearPolicyDecision.allow()

        required_facts: set[LinearPolicyFact] = set()
        validators: list[LinearPolicyValidator] = []
        for policy in policies:
            validators.extend(policy.validators)
            for validator in policy.validators:
                required_facts.update(validator.required_facts)

        try:
            context = self.load_facts(request, frozenset(required_facts))
        except LinearPolicyFactError as exc:
            return LinearPolicyDecision.deny(
                "CAO could not evaluate Linear agent policy because required facts were missing.",
                diagnostics={"missing_fact": exc.fact, "detail": exc.detail},
                policy_name="linear_policy_fact_hydration",
            )

        for validator in validators:
            decision = validator.check(context)
            if not decision.allowed:
                return LinearPolicyDecision.deny(
                    decision.reason,
                    diagnostics=decision.diagnostics,
                    policy_name=decision.policy_name or validator.name,
                )
        return LinearPolicyDecision.allow()


def build_default_linear_agent_policy_evaluator(
    presence: LinearPresence,
) -> LinearAgentPolicyEvaluator:
    """Return the code-defined Linear agent policy evaluator for one presence."""

    return LinearAgentPolicyEvaluator(
        registry=LinearAgentPolicyRegistry(DEFAULT_LINEAR_AGENT_POLICIES),
        load_facts=lambda request, required: load_linear_policy_facts(
            request,
            required,
            presence=presence,
        ),
    )


def load_linear_policy_facts(
    request: LinearPolicyRequest,
    required_facts: frozenset[LinearPolicyFact],
    *,
    presence: LinearPresence,
) -> LinearPolicyContext:
    """Load the requested Linear facts for policy validators."""

    issue = None
    if "issue" in required_facts:
        if not request.issue_id:
            raise LinearPolicyFactError("issue", "policy request has no issue id")
        issue = fetch_linear_issue_facts(request.issue_id, presence=presence)
    return LinearPolicyContext(request=request, issue=issue)


def fetch_linear_issue_facts(issue_id: str, *, presence: LinearPresence) -> LinearIssueFacts:
    """Fetch issue facts needed by Linear agent policy validators."""

    payload = app_client.linear_graphql(
        """
        query CaoLinearPolicyIssue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            description
            state { name type }
            team { key name }
            project { name }
            parent { identifier }
            delegate { name }
            assignee { name }
            labels(first: 50) {
              nodes { name }
            }
          }
        }
        """,
        {"id": issue_id},
        access_token=app_client.access_token_for_presence(presence),
        app_key=presence.app_key,
    )
    issue = payload.get("data", {}).get("issue")
    if not isinstance(issue, Mapping) or not issue.get("id"):
        raise LinearPolicyFactError("issue", f"Linear issue not found: {issue_id}")
    return _issue_facts_from_payload(issue)


def check_discovery_partner_can_receive_delegate(
    context: LinearPolicyContext,
) -> LinearPolicyDecision:
    """Deny only mechanically obvious downstream work for the front-door agent."""

    issue = context.require_issue()
    matched_labels = issue.matched_labels(DOWNSTREAM_DISCOVERY_LABELS)
    if matched_labels:
        return LinearPolicyDecision.deny(
            "Discovery Partner only accepts early discovery or shaping work. "
            "This issue has downstream execution labels.",
            diagnostics={"matched_labels": matched_labels},
        )

    normalized_state_type = _normalized_text(issue.state_type)
    if normalized_state_type in DOWNSTREAM_DISCOVERY_STATE_TYPES:
        return LinearPolicyDecision.deny(
            "Discovery Partner only accepts issues before downstream execution starts.",
            diagnostics={"state_type": issue.state_type},
        )

    normalized_state_name = _normalized_text(issue.state_name)
    if normalized_state_name in DOWNSTREAM_DISCOVERY_STATE_NAMES:
        return LinearPolicyDecision.deny(
            "Discovery Partner only accepts issues before downstream execution starts.",
            diagnostics={"state_name": issue.state_name},
        )

    marker = issue.contains_any_marker(DOWNSTREAM_DISCOVERY_MARKERS)
    if marker:
        return LinearPolicyDecision.deny(
            "Discovery Partner does not take already-bounded implementation or review handoffs.",
            diagnostics={"matched_marker": marker},
        )

    return LinearPolicyDecision.allow()


discovery_partner_can_receive_delegate = LinearPolicyValidator(
    name="discovery_partner_can_receive_delegate",
    required_facts=frozenset({"issue"}),
    check=check_discovery_partner_can_receive_delegate,
)

DEFAULT_LINEAR_AGENT_POLICIES = (
    LinearAgentPolicy(
        agent_id="discovery_partner",
        direction="incoming",
        action="delegate",
        validators=(discovery_partner_can_receive_delegate,),
    ),
    LinearAgentPolicy(
        agent_id="discovery_partner",
        direction="incoming",
        action="mention",
        validators=(discovery_partner_can_receive_delegate,),
    ),
)


def _issue_facts_from_payload(issue: Mapping[str, Any]) -> LinearIssueFacts:
    state = _mapping_value(issue.get("state"))
    team = _mapping_value(issue.get("team"))
    project = _mapping_value(issue.get("project"))
    parent = _mapping_value(issue.get("parent"))
    delegate = _mapping_value(issue.get("delegate"))
    assignee = _mapping_value(issue.get("assignee"))
    labels = _labels_from_payload(issue.get("labels"))
    return LinearIssueFacts(
        id=str(issue["id"]),
        identifier=_string_value(issue.get("identifier")),
        title=_string_value(issue.get("title")),
        description=_string_value(issue.get("description")),
        state_name=_string_value(state.get("name")),
        state_type=_string_value(state.get("type")),
        labels=labels,
        team_key=_string_value(team.get("key")),
        team_name=_string_value(team.get("name")),
        project_name=_string_value(project.get("name")),
        parent_identifier=_string_value(parent.get("identifier")),
        delegate_name=_string_value(delegate.get("name")),
        assignee_name=_string_value(assignee.get("name")),
    )


def _labels_from_payload(value: Any) -> tuple[str, ...]:
    labels: list[str] = []
    if isinstance(value, Mapping):
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, Mapping):
                    label = _string_value(node.get("name"))
                    if label:
                        labels.append(label)
    return tuple(labels)


def _mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _normalized_text(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().lower().split())
