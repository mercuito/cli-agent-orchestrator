"""Compatibility facade for inbox persistence.

The authoritative inbox persistence implementation lives in
``cli_agent_orchestrator.inbox.store``. This module preserves the historic
``clients.database`` import surface while callers migrate to the inbox package.
"""

from cli_agent_orchestrator.inbox.store import *  # noqa: F401,F403
