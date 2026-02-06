"""Agent profile models."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from cli_agent_orchestrator.models.provider import ProviderType


class McpServer(BaseModel):
    """MCP server configuration."""

    type: Optional[str] = None
    command: str
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    timeout: Optional[int] = None


class AgentProfile(BaseModel):
    """Agent profile configuration with Q CLI agent fields."""

    model_config = ConfigDict(use_enum_values=True)

    name: str
    description: str
    system_prompt: Optional[str] = None  # The markdown content

    # Worker-pool routing metadata (optional)
    provider: Optional[ProviderType] = None
    role: Optional[str] = None
    tags: Optional[List[str]] = None

    class ReasoningEffort(str, Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    reasoning_effort: Optional[ReasoningEffort] = None

    # Q CLI agent fields (all optional, will be passed through to JSON)
    prompt: Optional[str] = None
    mcpServers: Optional[Dict[str, Any]] = None
    tools: Optional[List[str]] = Field(default=None)
    toolAliases: Optional[Dict[str, str]] = None
    allowedTools: Optional[List[str]] = None
    toolsSettings: Optional[Dict[str, Any]] = None
    resources: Optional[List[str]] = None
    hooks: Optional[Dict[str, Any]] = None
    useLegacyMcpJson: Optional[bool] = None
    model: Optional[str] = None
    codexConfig: Optional[Dict[str, Any]] = None
