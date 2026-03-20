"""
Simulation Runner - Orchestrate multi-user, multi-session simulations.

This module provides tools for running complex simulation scenarios
that test memoir integration patterns across multiple users and sessions.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from memoir.simulation.agent import Agent, AgentConfig, AgentResponse, MockAgent
from memoir.simulation.cli_executor import CLIExecutor
from memoir.simulation.session import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class ConversationStep:
    """A single step in a conversation scenario."""

    user_message: str
    expected_tool_calls: list[str] = field(default_factory=list)
    expected_memory_recall: bool = False
    assertions: list[str] = field(
        default_factory=list
    )  # Python expressions to evaluate
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserScenario:
    """A scenario for a single user."""

    user_id: str
    steps: list[ConversationStep] = field(default_factory=list)
    initial_memories: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """
    A complete simulation scenario.

    Defines multiple users, their conversations, and expected behaviors.
    """

    name: str
    description: str = ""
    users: list[UserScenario] = field(default_factory=list)
    setup_commands: list[str] = field(default_factory=list)
    teardown_commands: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Scenario":
        """Create scenario from dict."""
        users = []
        for user_data in data.get("users", []):
            steps = [
                ConversationStep(
                    user_message=s["user_message"],
                    expected_tool_calls=s.get("expected_tool_calls", []),
                    expected_memory_recall=s.get("expected_memory_recall", False),
                    assertions=s.get("assertions", []),
                    metadata=s.get("metadata", {}),
                )
                for s in user_data.get("steps", [])
            ]
            users.append(
                UserScenario(
                    user_id=user_data["user_id"],
                    steps=steps,
                    initial_memories=user_data.get("initial_memories", []),
                    metadata=user_data.get("metadata", {}),
                )
            )

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            users=users,
            setup_commands=data.get("setup_commands", []),
            teardown_commands=data.get("teardown_commands", []),
            config=data.get("config", {}),
        )

    @classmethod
    def from_json_file(cls, path: str) -> "Scenario":
        """Load scenario from JSON file."""
        with open(path) as f:
            return cls.from_dict(json.load(f))


@dataclass
class StepResult:
    """Result from executing a conversation step."""

    step_index: int
    user_message: str
    response: AgentResponse
    passed_assertions: list[str] = field(default_factory=list)
    failed_assertions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class UserResult:
    """Result from running a user scenario."""

    user_id: str
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = True
    errors: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Result from running a complete scenario."""

    scenario_name: str
    users: list[UserResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = True
    setup_success: bool = True
    teardown_success: bool = True
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Get summary of results."""
        total_steps = sum(len(u.steps) for u in self.users)
        passed_steps = sum(
            1
            for u in self.users
            for s in u.steps
            if not s.failed_assertions and not s.errors
        )

        return {
            "scenario": self.scenario_name,
            "success": self.success,
            "total_users": len(self.users),
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": total_steps - passed_steps,
            "duration_ms": self.total_duration_ms,
        }


class SimulationRunner:
    """
    Run simulation scenarios for memoir integration testing.

    Orchestrates multi-user conversations with agents, executing
    scenarios and collecting results for verification.

    Example:
        runner = SimulationRunner(
            store_path="/tmp/memoir-test",
            model="gpt-4o-mini",
        )

        # Define a scenario
        scenario = Scenario(
            name="User Preferences",
            users=[
                UserScenario(
                    user_id="alice",
                    steps=[
                        ConversationStep(
                            user_message="I prefer dark mode",
                            expected_tool_calls=["memoir_remember"],
                        ),
                        ConversationStep(
                            user_message="What are my preferences?",
                            expected_memory_recall=True,
                        ),
                    ],
                ),
            ],
        )

        # Run the scenario
        result = await runner.run_scenario(scenario)
        print(result.summary())
    """

    def __init__(
        self,
        store_path: str,
        model: str = "gpt-4o-mini",
        use_mock_agent: bool = False,
        session_persistence_dir: Optional[str] = None,
    ):
        """
        Initialize simulation runner.

        Args:
            store_path: Path to memoir store
            model: LLM model to use
            use_mock_agent: Use mock agent instead of real LLM
            session_persistence_dir: Directory for session persistence
        """
        self.store_path = store_path
        self.model = model
        self.use_mock_agent = use_mock_agent

        self.cli = CLIExecutor(store_path)
        self.session_manager = SessionManager(session_persistence_dir)
        self.agents: dict[str, Agent] = {}

    async def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        """
        Run a complete simulation scenario.

        Args:
            scenario: Scenario to run

        Returns:
            ScenarioResult with all outcomes
        """
        start_time = time.time()
        result = ScenarioResult(scenario_name=scenario.name)

        # Run setup commands
        result.setup_success = self._run_setup(scenario.setup_commands)
        if not result.setup_success:
            result.success = False
            result.errors.append("Setup failed")
            return result

        try:
            # Run user scenarios in parallel
            user_tasks = [
                self._run_user_scenario(user_scenario, scenario.config)
                for user_scenario in scenario.users
            ]
            user_results = await asyncio.gather(*user_tasks, return_exceptions=True)

            for i, user_result in enumerate(user_results):
                if isinstance(user_result, Exception):
                    result.users.append(
                        UserResult(
                            user_id=scenario.users[i].user_id,
                            success=False,
                            errors=[str(user_result)],
                        )
                    )
                    result.success = False
                else:
                    result.users.append(user_result)
                    if not user_result.success:
                        result.success = False

        finally:
            # Run teardown commands
            result.teardown_success = self._run_teardown(scenario.teardown_commands)

        result.total_duration_ms = (time.time() - start_time) * 1000
        return result

    async def _run_user_scenario(
        self,
        user_scenario: UserScenario,
        config: dict,
    ) -> UserResult:
        """Run a single user's scenario."""
        start_time = time.time()
        result = UserResult(user_id=user_scenario.user_id)

        # Create agent for this user
        agent = self._get_or_create_agent(user_scenario.user_id, config)
        agent.start_session()

        # Seed initial memories
        for memory in user_scenario.initial_memories:
            self.cli.remember(
                content=memory.get("content", ""),
                namespace=memory.get("namespace", f"user_id:{user_scenario.user_id}"),
            )

        # Run conversation steps
        for i, step in enumerate(user_scenario.steps):
            try:
                step_result = await self._run_step(agent, i, step)
                result.steps.append(step_result)

                if step_result.failed_assertions or step_result.errors:
                    result.success = False

            except Exception as e:
                logger.error(f"Step {i} failed: {e}")
                result.steps.append(
                    StepResult(
                        step_index=i,
                        user_message=step.user_message,
                        response=AgentResponse(content=""),
                        errors=[str(e)],
                    )
                )
                result.success = False

        # End session
        agent.end_session()

        result.total_duration_ms = (time.time() - start_time) * 1000
        return result

    async def _run_step(
        self,
        agent: Agent,
        step_index: int,
        step: ConversationStep,
    ) -> StepResult:
        """Run a single conversation step."""
        response = await agent.chat(step.user_message)

        result = StepResult(
            step_index=step_index,
            user_message=step.user_message,
            response=response,
        )

        # Check expected tool calls
        if step.expected_tool_calls:
            actual_tools = [tc.name for tc in response.tool_calls]
            for expected in step.expected_tool_calls:
                if expected in actual_tools:
                    result.passed_assertions.append(f"Tool '{expected}' was called")
                else:
                    result.failed_assertions.append(
                        f"Expected tool '{expected}' was not called"
                    )

        # Check memory recall
        if step.expected_memory_recall:
            if response.memory_context:
                result.passed_assertions.append("Memory was recalled")
            else:
                result.failed_assertions.append("Expected memory recall did not occur")

        # Run custom assertions
        for assertion in step.assertions:
            try:
                # Create evaluation context
                context = {
                    "response": response,
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "tool_results": response.tool_results,
                    "memory_context": response.memory_context,
                }
                if eval(assertion, {"__builtins__": {}}, context):
                    result.passed_assertions.append(assertion)
                else:
                    result.failed_assertions.append(assertion)
            except Exception as e:
                result.errors.append(f"Assertion error '{assertion}': {e}")

        return result

    def _get_or_create_agent(self, user_id: str, config: dict) -> Agent:
        """Get or create agent for a user."""
        if user_id not in self.agents:
            agent_config = AgentConfig(
                store_path=self.store_path,
                model=config.get("model", self.model),
                **{
                    k: v
                    for k, v in config.items()
                    if k in AgentConfig.__dataclass_fields__
                },
            )

            if self.use_mock_agent:
                self.agents[user_id] = MockAgent(
                    config=agent_config,
                    user_id=user_id,
                    session_manager=self.session_manager,
                )
            else:
                self.agents[user_id] = Agent(
                    config=agent_config,
                    user_id=user_id,
                    session_manager=self.session_manager,
                )

        return self.agents[user_id]

    def _run_setup(self, commands: list[str]) -> bool:
        """Run setup commands."""
        for cmd in commands:
            try:
                # Parse and execute command
                parts = cmd.split()
                if not parts:
                    continue

                if parts[0] == "memoir":
                    # Execute via CLI
                    result = self.cli._execute(parts[1:])
                    if not result.success:
                        logger.error(f"Setup command failed: {cmd}")
                        return False
            except Exception as e:
                logger.error(f"Setup error: {e}")
                return False

        return True

    def _run_teardown(self, commands: list[str]) -> bool:
        """Run teardown commands."""
        for cmd in commands:
            try:
                parts = cmd.split()
                if not parts:
                    continue

                if parts[0] == "memoir":
                    self.cli._execute(parts[1:])
            except Exception as e:
                logger.error(f"Teardown error: {e}")
                # Don't fail on teardown errors

        return True


# =============================================================================
# Example Scenarios
# =============================================================================


def create_example_scenarios() -> list[Scenario]:
    """Create example scenarios for testing."""

    # Scenario 1: Single user preference storage
    preference_scenario = Scenario(
        name="User Preferences",
        description="Test storing and recalling user preferences",
        users=[
            UserScenario(
                user_id="alice",
                steps=[
                    ConversationStep(
                        user_message="I prefer dark mode and vim keybindings",
                    ),
                    ConversationStep(
                        user_message="What do you remember about my preferences?",
                        expected_memory_recall=True,
                    ),
                ],
            ),
        ],
    )

    # Scenario 2: Multi-user isolation
    multiuser_scenario = Scenario(
        name="Multi-User Isolation",
        description="Test that user memories are properly isolated",
        users=[
            UserScenario(
                user_id="bob",
                steps=[
                    ConversationStep(
                        user_message="Remember that I'm working on Project Alpha",
                    ),
                ],
            ),
            UserScenario(
                user_id="carol",
                steps=[
                    ConversationStep(
                        user_message="What project am I working on?",
                        assertions=[
                            "'Alpha' not in content.lower()",  # Should not see Bob's project
                        ],
                    ),
                ],
            ),
        ],
    )

    # Scenario 3: Cross-session recall
    session_scenario = Scenario(
        name="Cross-Session Recall",
        description="Test that memories persist across sessions",
        users=[
            UserScenario(
                user_id="dave",
                initial_memories=[
                    {
                        "content": "User Dave prefers Python over JavaScript",
                        "namespace": "user:dave",
                    },
                ],
                steps=[
                    ConversationStep(
                        user_message="Previously I told you about my language preferences. What were they?",
                        expected_memory_recall=True,
                    ),
                ],
            ),
        ],
    )

    return [preference_scenario, multiuser_scenario, session_scenario]


async def run_example():
    """Run example simulation."""
    import tempfile

    # Create temporary store
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = f"{tmpdir}/memoir-test"

        # Initialize store
        cli = CLIExecutor(store_path)
        cli.new(store_path)

        # Create runner with mock agent for testing
        runner = SimulationRunner(
            store_path=store_path,
            use_mock_agent=True,
        )

        # Run example scenario
        scenarios = create_example_scenarios()
        for scenario in scenarios:
            print(f"\n{'='*60}")
            print(f"Running: {scenario.name}")
            print(f"{'='*60}")

            result = await runner.run_scenario(scenario)
            summary = result.summary()

            print(f"Result: {'PASSED' if result.success else 'FAILED'}")
            print(f"Users: {summary['total_users']}")
            print(f"Steps: {summary['passed_steps']}/{summary['total_steps']} passed")
            print(f"Duration: {summary['duration_ms']:.1f}ms")


if __name__ == "__main__":
    asyncio.run(run_example())
