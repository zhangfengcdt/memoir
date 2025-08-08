"""
Example of integrating semantic classification with agent workflows.
Demonstrates how to use the LLM-based taxonomy system in production agents.
"""

import asyncio
import time
from typing import Optional

from langmem_prollytree.taxonomy.dynamic_taxonomy import DynamicTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier


class MockLLMResponse:
    """Mock response object for agent demonstration."""

    def __init__(self, content: str):
        self.content = content


class AgentLLM:
    """Mock LLM that simulates agent-style responses."""

    async def ainvoke(self, prompt: str) -> MockLLMResponse:
        """Simulate agent LLM with context-aware responses."""
        content_lower = prompt.lower()

        # Agent-specific classifications
        if "user" in content_lower and (
            "said" in content_lower or "told" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "context.current.conversation.user_input",
                "confidence": 0.85,
                "alternative_paths": ["context.current.session"],
                "reasoning": "User input during conversation"
            }"""
            )
        elif "agent" in content_lower and (
            "responded" in content_lower or "replied" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "context.current.conversation.agent_response",
                "confidence": 0.85,
                "alternative_paths": ["context.current.session"],
                "reasoning": "Agent response during conversation"
            }"""
            )
        elif (
            "task" in content_lower
            or "goal" in content_lower
            or "objective" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "goals.current.task.primary",
                "confidence": 0.90,
                "alternative_paths": ["goals.current"],
                "reasoning": "Current task or objective"
            }"""
            )
        elif (
            "error" in content_lower
            or "failed" in content_lower
            or "problem" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "context.system.errors.runtime",
                "confidence": 0.85,
                "alternative_paths": ["context.system"],
                "reasoning": "System error or failure"
            }"""
            )
        elif (
            "learned" in content_lower
            or "discovered" in content_lower
            or "found" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "knowledge.discovered.session",
                "confidence": 0.80,
                "alternative_paths": ["knowledge.discovered"],
                "reasoning": "New knowledge or discovery"
            }"""
            )
        elif (
            "preference" in content_lower
            or "like" in content_lower
            or "prefer" in content_lower
        ):
            return MockLLMResponse(
                """{
                "primary_path": "preferences.user.behavior.interaction",
                "confidence": 0.75,
                "alternative_paths": ["preferences.user"],
                "reasoning": "User preferences and behavior"
            }"""
            )
        else:
            return MockLLMResponse(
                """{
                "primary_path": "context.current.session.topic.main",
                "confidence": 0.60,
                "alternative_paths": ["context.current.session"],
                "reasoning": "General session context"
            }"""
            )


class AgentWithSemanticMemory:
    """
    Example agent using semantic classification for memory organization.
    Shows how to integrate with production agent workflows.
    """

    def __init__(self, agent_id: str = "agent_001"):
        self.agent_id = agent_id

        # Initialize semantic classification system
        print(f"🤖 Initializing agent {agent_id} with semantic memory...")
        llm = AgentLLM()
        classifier = SemanticClassifier(llm=llm)
        self.taxonomy = DynamicTaxonomy(
            classifier=classifier,
            confidence_threshold=0.65,  # Higher threshold for agent contexts
            expansion_threshold=8,  # Smaller threshold for quicker expansion
            enable_other_categories=True,
        )

        # Agent state
        self.current_user = None
        self.session_context = {}
        self.memory_buffer = []

        print(
            f"   ✅ Agent {agent_id} ready with {self.taxonomy.get_statistics()['total_paths']} taxonomy paths"
        )

    async def start_user_session(self, user_id: str, context: Optional[dict] = None):
        """Start a new user session."""
        self.current_user = user_id
        self.session_context = context or {}

        # Store session start
        session_memory = f"User session started for {user_id}"
        if context:
            session_memory += f" with context: {context}"

        await self.store_memory(session_memory, memory_type="session_start")

        print(f"🚀 Started session for user {user_id}")

    async def store_memory(
        self,
        content: str,
        memory_type: str = "general",
        metadata: Optional[dict] = None,
    ):
        """Store a memory with semantic classification."""
        # Enhance content with type information for better classification
        enhanced_content = f"{memory_type}: {content}"

        # Add session context
        full_metadata = {
            "user_id": self.current_user,
            "agent_id": self.agent_id,
            "memory_type": memory_type,
            "session_context": self.session_context,
            **(metadata or {}),
        }

        start_time = time.time()

        # Classify and store
        path, confidence = await self.taxonomy.classify_with_fallback(
            enhanced_content, full_metadata
        )

        classification_time = (time.time() - start_time) * 1000

        # Add to memory buffer
        memory_entry = {
            "content": content,
            "enhanced_content": enhanced_content,
            "path": path,
            "confidence": confidence,
            "metadata": full_metadata,
            "timestamp": time.time(),
            "classification_time_ms": classification_time,
        }

        self.memory_buffer.append(memory_entry)

        status = "✅" if confidence >= self.taxonomy.confidence_threshold else "⚠️"
        print(
            f"   {status} Stored '{content[:50]}...' → {path} ({confidence:.2f}, {classification_time:.1f}ms)"
        )

        return memory_entry

    async def process_user_input(self, user_input: str):
        """Process user input and store relevant memories."""
        await self.store_memory(
            f"User said: {user_input}",
            memory_type="user_input",
            metadata={"input_length": len(user_input)},
        )

    async def process_agent_response(
        self, agent_response: str, reasoning: Optional[str] = None
    ):
        """Process agent response and store relevant memories."""
        await self.store_memory(
            f"Agent responded: {agent_response}",
            memory_type="agent_response",
            metadata={"reasoning": reasoning, "response_length": len(agent_response)},
        )

    async def handle_task_completion(
        self, task_description: str, result: str, success: bool
    ):
        """Handle task completion and store results."""
        status = "successfully completed" if success else "failed"
        memory_content = f"Task '{task_description}' {status}: {result}"

        await self.store_memory(
            memory_content,
            memory_type="task_completion",
            metadata={"task": task_description, "success": success, "result": result},
        )

    async def handle_error(
        self, error_type: str, error_message: str, context: Optional[dict] = None
    ):
        """Handle and store error information."""
        await self.store_memory(
            f"Error occurred - {error_type}: {error_message}",
            memory_type="error",
            metadata={"error_type": error_type, "error_context": context},
        )

    async def learn_from_interaction(
        self, discovery: str, source: str = "user_interaction"
    ):
        """Store learning and discoveries."""
        await self.store_memory(
            f"Learned: {discovery}", memory_type="learning", metadata={"source": source}
        )

    async def get_memory_summary(self) -> dict:
        """Get a summary of stored memories."""
        if not self.memory_buffer:
            return {"total": 0, "message": "No memories stored"}

        # Analyze memory buffer
        total_memories = len(self.memory_buffer)
        avg_confidence = (
            sum(m["confidence"] for m in self.memory_buffer) / total_memories
        )
        avg_classification_time = (
            sum(m["classification_time_ms"] for m in self.memory_buffer)
            / total_memories
        )

        # Group by path
        path_counts = {}
        type_counts = {}
        for memory in self.memory_buffer:
            path = memory["path"]
            memory_type = memory["metadata"].get("memory_type", "unknown")
            path_counts[path] = path_counts.get(path, 0) + 1
            type_counts[memory_type] = type_counts.get(memory_type, 0) + 1

        # Taxonomy statistics
        taxonomy_stats = self.taxonomy.get_statistics()

        return {
            "total_memories": total_memories,
            "avg_confidence": avg_confidence,
            "avg_classification_time_ms": avg_classification_time,
            "path_distribution": dict(
                sorted(path_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "type_distribution": dict(
                sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "taxonomy_stats": taxonomy_stats,
            "high_confidence_count": sum(
                1 for m in self.memory_buffer if m["confidence"] >= 0.8
            ),
            "low_confidence_count": sum(
                1 for m in self.memory_buffer if m["confidence"] < 0.6
            ),
        }

    async def end_session(self):
        """End the current session and provide summary."""
        if self.current_user:
            await self.store_memory(
                f"User session ended for {self.current_user}", memory_type="session_end"
            )

        summary = await self.get_memory_summary()

        print(f"📊 Session ended for user {self.current_user}")
        print(f"   • Total memories: {summary['total_memories']}")
        print(f"   • Average confidence: {summary['avg_confidence']:.2f}")
        print(
            f"   • Average classification time: {summary['avg_classification_time_ms']:.1f}ms"
        )

        # Clear session data
        self.current_user = None
        self.session_context = {}

        return summary


async def demonstrate_agent_workflow():
    """Demonstrate agent workflow with semantic memory."""
    print("=" * 80)
    print("Agent Workflow with Semantic Memory Demonstration")
    print("=" * 80)

    # Initialize agent
    agent = AgentWithSemanticMemory("customer_support_agent")

    # Simulate customer support session
    await agent.start_user_session(
        "customer_123", context={"channel": "web_chat", "tier": "premium"}
    )

    print("\n1. CUSTOMER INTERACTION SIMULATION")
    print("-" * 50)

    # Simulate conversation flow
    interactions = [
        ("user_input", "I'm having trouble with my account login"),
        (
            "agent_response",
            "I understand you're having login issues. Let me help you with that.",
            "troubleshoot_login",
        ),
        ("user_input", "I tried resetting my password but didn't receive the email"),
        (
            "agent_response",
            "Let me check your email settings and resend that reset link.",
            "email_verification",
        ),
        (
            "learning",
            "Customer prefers immediate email notifications",
            "interaction_pattern",
        ),
        (
            "task_completion",
            "Password reset email resent",
            "Email delivered successfully",
            True,
        ),
        ("user_input", "Perfect! I got the email and reset my password"),
        (
            "agent_response",
            "Great! Is there anything else I can help you with today?",
            "session_wrap_up",
        ),
        (
            "learning",
            "Password reset emails may have delivery delays",
            "system_observation",
        ),
    ]

    for interaction_type, content, *extra in interactions:
        if interaction_type == "user_input":
            await agent.process_user_input(content)
        elif interaction_type == "agent_response":
            reasoning = extra[0] if extra else None
            await agent.process_agent_response(content, reasoning)
        elif interaction_type == "task_completion":
            result, success = extra[0], extra[1]
            await agent.handle_task_completion(
                "Password reset assistance", result, success
            )
        elif interaction_type == "learning":
            source = extra[0] if extra else "interaction"
            await agent.learn_from_interaction(content, source)

    print("\n2. ERROR HANDLING SIMULATION")
    print("-" * 50)

    # Simulate some errors
    await agent.handle_error(
        "api_timeout",
        "Email service timeout after 30s",
        {"service": "email_api", "timeout_ms": 30000},
    )
    await agent.handle_error(
        "validation_error", "Invalid email format provided", {"email": "invalid_format"}
    )

    print("\n3. MEMORY ANALYSIS")
    print("-" * 50)

    summary = await agent.get_memory_summary()

    print("Session Memory Summary:")
    print(f"   • Total memories stored: {summary['total_memories']}")
    print(f"   • Average confidence: {summary['avg_confidence']:.2f}")
    print(
        f"   • Average classification time: {summary['avg_classification_time_ms']:.1f}ms"
    )
    print(f"   • High confidence (≥0.8): {summary['high_confidence_count']}")
    print(f"   • Low confidence (<0.6): {summary['low_confidence_count']}")

    print("\nMemory Types Distribution:")
    for memory_type, count in summary["type_distribution"].items():
        percentage = (count / summary["total_memories"]) * 100
        print(f"   • {memory_type}: {count} ({percentage:.1f}%)")

    print("\nTop Semantic Paths:")
    for path, count in list(summary["path_distribution"].items())[:5]:
        percentage = (count / summary["total_memories"]) * 100
        print(f"   • {path}: {count} ({percentage:.1f}%)")

    print("\nTaxonomy State:")
    taxonomy_stats = summary["taxonomy_stats"]
    print(f"   • Total paths: {taxonomy_stats['total_paths']}")
    print(f"   • Items in 'other': {taxonomy_stats['unclassified_items']}")

    if taxonomy_stats["unclassified_items"] > 0:
        expansion_ready = (
            taxonomy_stats["unclassified_items"] >= agent.taxonomy.expansion_threshold
        )
        print(f"   • Expansion ready: {'Yes' if expansion_ready else 'No'}")
        if expansion_ready:
            print("     🔄 Taxonomy would be expanded in production")

    print("\n4. PRODUCTION INTEGRATION NOTES")
    print("-" * 50)
    print("✅ Agent memories are semantically organized")
    print("✅ Classification adapts to agent-specific contexts")
    print("✅ Error handling creates searchable knowledge base")
    print("✅ Learning insights are automatically categorized")
    print("✅ Session context enhances classification accuracy")

    print("\n💡 Integration Tips:")
    print("   1. Replace AgentLLM with your production LLM")
    print("   2. Connect to actual memory storage (database, vector store)")
    print("   3. Use agent-specific confidence thresholds")
    print("   4. Implement background taxonomy expansion")
    print("   5. Add memory retrieval for context-aware responses")

    # End session
    final_summary = await agent.end_session()

    print("\n🎉 Agent workflow demonstration completed!")
    print(f"   Processed {final_summary['total_memories']} memories in session")


async def main():
    """Run the complete agent integration demonstration."""
    await demonstrate_agent_workflow()


if __name__ == "__main__":
    asyncio.run(main())
