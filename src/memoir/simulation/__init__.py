"""
Memoir Agent Simulation Framework.

A POC framework for simulating agent interactions with memoir memory,
designed to test OpenClaw-style integration patterns.

Components:
- CLIExecutor: Execute memoir CLI commands and return results
- HookSystem: Event-driven hooks for memoir operations
- SkillInjector: Inject memoir skill instructions into agent prompts
- Session: Manage user sessions with namespaces
- Agent: Simulate LLM-powered agent with memoir integration
- SimulationRunner: Orchestrate multi-user, multi-session simulations
"""

from memoir.simulation.agent import Agent, AgentConfig, MockAgent
from memoir.simulation.cli_executor import CLIExecutor, CLIResult
from memoir.simulation.hooks import HookEvent, HookResult, HookSystem
from memoir.simulation.live_tui import (
    EventSource,
    InstrumentedHookSystem,
    InstrumentedSkillInjector,
    LiveSimulationTUI,
    MemoryEvent,
)
from memoir.simulation.real_llm_agent import RealLLMAgent
from memoir.simulation.runner import Scenario, SimulationRunner
from memoir.simulation.session import Session, SessionManager
from memoir.simulation.skill import SkillInjector

__all__ = [
    "Agent",
    "AgentConfig",
    "CLIExecutor",
    "CLIResult",
    "EventSource",
    "HookEvent",
    "HookResult",
    "HookSystem",
    "InstrumentedHookSystem",
    "InstrumentedSkillInjector",
    "LiveSimulationTUI",
    "MemoryEvent",
    "MockAgent",
    "RealLLMAgent",
    "Scenario",
    "Session",
    "SessionManager",
    "SimulationRunner",
    "SkillInjector",
]
