"""Additional API tests to maximize patch coverage.

Covers: WebSocket localhost guard, list_all_terminals endpoint,
flow path traversal validation, and remaining error branches.
"""

from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.api.main import CreateFlowRequest, app


class TestFlowNameValidation:
    """Test CreateFlowRequest.validate_name blocks path traversal."""

    @pytest.mark.parametrize(
        "bad_name",
        ["../../etc/cron", "../evil", "foo/bar", "a\\b", ".."],
    )
    def test_rejects_traversal_names(self, bad_name):
        with pytest.raises(Exception):
            CreateFlowRequest(
                name=bad_name,
                schedule="0 * * * *",
                agent_id="dev",
                prompt_template="x",
            )

    @pytest.mark.parametrize(
        "good_name",
        ["my-flow", "nightly_build", "FLOW123", "a.b"],
    )
    def test_accepts_safe_names(self, good_name):
        req = CreateFlowRequest(
            name=good_name,
            schedule="0 * * * *",
            agent_id="dev",
            prompt_template="x",
        )
        assert req.name == good_name


class TestRemovedAgentProfileEndpoint:
    """The old profile listing endpoint is removed by the agent cutover."""

    def test_profiles_endpoint_is_removed(self, client):
        resp = client.get("/agents/profiles")

        assert resp.status_code == 404
