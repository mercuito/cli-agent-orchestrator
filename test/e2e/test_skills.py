"""End-to-end tests for the skill content API.

Provider-neutral skills are source artifacts that providers may materialize
into native runtime storage. CAO does not inject a global skill catalog into
agent prompts.
"""

import pytest
import requests

from cli_agent_orchestrator.cli.commands.init import seed_default_skills
from cli_agent_orchestrator.constants import API_BASE_URL


@pytest.fixture(scope="module", autouse=True)
def ensure_skills_seeded():
    """Seed default skills so API tests have content to read."""
    seed_default_skills()


@pytest.mark.e2e
class TestSkillApi:
    """E2E tests for the skill content REST API endpoint."""

    def test_get_skill_returns_content(self):
        """GET /skills/{name} returns the full Markdown body of an installed skill."""
        resp = requests.get(f"{API_BASE_URL}/skills/cao-worker-protocols")
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code} {resp.text}"

        data = resp.json()
        assert data["name"] == "cao-worker-protocols"
        assert (
            "send_message" in data["content"]
        ), f"Skill content should mention send_message. Got: {data['content'][:200]}"

    def test_get_skill_missing_returns_404(self):
        """GET /skills/{name} returns 404 for a nonexistent skill."""
        resp = requests.get(f"{API_BASE_URL}/skills/nonexistent-skill")
        assert resp.status_code == 404

    def test_get_skill_traversal_returns_400(self):
        """GET /skills/{name} rejects path traversal attempts."""
        resp = requests.get(f"{API_BASE_URL}/skills/../../../etc/passwd")
        assert resp.status_code in (400, 404, 422)
