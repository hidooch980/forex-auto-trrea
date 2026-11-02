"""Typed, provenance-carrying contracts for specialist agent outputs."""
from .contracts import AgentOutput, validate_agent_output

__all__ = ["AgentOutput", "validate_agent_output"]
