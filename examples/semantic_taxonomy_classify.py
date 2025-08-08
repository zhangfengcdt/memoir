#!/usr/bin/env python3
"""
Production-ready integration example showing how to use the dynamic taxonomy
with LLM-based classification and intelligent routing.
"""

import asyncio
import time
from typing import Optional

from langmem_prollytree.taxonomy.dynamic_taxonomy import DynamicTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier


class MockLLMResponse:
    """Mock response object with .content attribute like LangChain messages."""

    def __init__(self, content: str):
        self.content = content


class MockLLM:
    """Mock LLM implementing LangChain interface for demonstration purposes."""

    async def ainvoke(self, prompt: str) -> MockLLMResponse:
        """Mock LLM response implementing LangChain ainvoke interface."""
        # Parse the prompt to extract memory content
        if "Memory to classify:" in prompt:
            content_start = prompt.find("Memory to classify:") + len(
                "Memory to classify:"
            )
            content_line = prompt[content_start:].split("\n")[0].strip()
            memory_content = content_line.strip('"')
        else:
            memory_content = prompt[:50]  # Fallback

        # Simple mock logic to demonstrate different confidence levels
        if any(word in memory_content.lower() for word in ["name", "work", "prefer"]):
            if "work" in memory_content.lower():
                content = """{
                    "primary_path": "profile.professional.current.role",
                    "confidence": 0.85,
                    "alternative_paths": ["profile.professional.experience"],
                    "reasoning": "High confidence classification for professional information"
                }"""
            elif "name" in memory_content.lower():
                content = """{
                    "primary_path": "profile.personal.identity.name",
                    "confidence": 0.85,
                    "alternative_paths": ["profile.personal.identity"],
                    "reasoning": "High confidence classification for personal identity"
                }"""
            else:  # "prefer"
                content = """{
                    "primary_path": "preferences.technical.programming.language",
                    "confidence": 0.85,
                    "alternative_paths": ["preferences.technical"],
                    "reasoning": "High confidence classification for technical preferences"
                }"""
            return MockLLMResponse(content)
        elif len(memory_content.split()) > 15:
            content = """{
                "primary_path": "experience.professional.projects",
                "confidence": 0.45,
                "alternative_paths": ["experience.professional.other"],
                "reasoning": "Complex content with moderate confidence"
            }"""
            return MockLLMResponse(content)
        else:
            content = """{
                "primary_path": "context.other",
                "confidence": 0.3,
                "alternative_paths": [],
                "reasoning": "Unusual content, routing to other category for future classification"
            }"""
            return MockLLMResponse(content)


class SmartMemorySystem:
    """
    Production-ready memory system with intelligent LLM-based classification.
    """

    def __init__(
        self,
        llm=None,
        confidence_threshold: float = 0.5,
        expansion_threshold: int = 10,
    ):
        """
        Initialize smart memory system.

        Args:
            llm: LLM instance for classification (uses MockLLM if None)
            confidence_threshold: Min confidence for direct classification
            expansion_threshold: Items in 'other' before expansion
        """
        # Use provided LLM or create mock for demo
        if llm is None:
            print(
                "⚠️  Using MockLLM for demonstration. In production, provide real LLM instance."
            )
            llm = MockLLM()

        classifier = SemanticClassifier(llm=llm)
        self.taxonomy = DynamicTaxonomy(
            classifier=classifier,
            expansion_threshold=expansion_threshold,
            confidence_threshold=confidence_threshold,
        )

        self.confidence_threshold = confidence_threshold

        # Metrics tracking
        self.metrics = {
            "direct_classifications": 0,
            "fallback_classifications": 0,
            "other_assignments": 0,
            "expansions_triggered": 0,
        }

    async def classify_memory(
        self,
        content: str,
        metadata: Optional[dict] = None,
        use_fallback: bool = True,
    ) -> tuple[str, float, str]:
        """
        Classify memory using LLM-based classification.

        Args:
            content: Memory content to classify
            metadata: Optional metadata
            use_fallback: Use fallback to 'other' categories for low confidence

        Returns:
            Tuple of (path, confidence, method_used)
        """
        start = time.time()

        if use_fallback:
            # Use fallback system with 'other' categories
            path, confidence = await self.taxonomy.classify_with_fallback(
                content, metadata
            )
            method = "fallback" if path.endswith(".other") else "direct"
            self.metrics["fallback_classifications"] += 1
        else:
            # Direct LLM classification only
            path, confidence = await self.taxonomy.classify_with_llm(content, metadata)
            method = "direct"
            self.metrics["direct_classifications"] += 1

        elapsed = time.time() - start

        # Track 'other' assignments
        if path.endswith(".other"):
            self.metrics["other_assignments"] += 1
            print(f"⚠️  Routed to 'other' category: {path}")

        print(f"🤖 LLM Classification ({method}): {elapsed*1000:.2f}ms")
        print(f"   Content: '{content[:50]}...'")
        print(f"   Path: {path}")
        print(f"   Confidence: {confidence:.2f}")

        return path, confidence, method

    async def process_batch(self, memories: list[str]) -> dict:
        """
        Process a batch of memories with intelligent routing.

        Args:
            memories: List of memory contents

        Returns:
            Processing results with statistics
        """
        results = []

        for memory in memories:
            path, confidence, method = await self.classify_memory(memory)
            results.append(
                {
                    "content": memory[:50] + "...",
                    "path": path,
                    "confidence": confidence,
                    "method": method,
                }
            )

        # Check for expansion opportunities
        await self._check_expansions()

        return {
            "results": results,
            "metrics": self.get_metrics(),
        }

    async def _check_expansions(self):
        """Check if any 'other' categories need expansion."""
        for path, node in self.taxonomy.path_index.items():
            if (
                path.endswith(".other")
                and len(node.other_items) >= self.taxonomy.expansion_threshold
            ):
                print(
                    f"🔄 Triggering expansion for {path} ({len(node.other_items)} items)"
                )
                await self.taxonomy.expand_taxonomy(path)
                self.metrics["expansions_triggered"] += 1

    def get_metrics(self) -> dict:
        """Get system metrics."""
        total = (
            self.metrics["direct_classifications"]
            + self.metrics["fallback_classifications"]
        )

        if total == 0:
            return self.metrics

        return {
            **self.metrics,
            "direct_percentage": (self.metrics["direct_classifications"] / total) * 100,
            "fallback_percentage": (self.metrics["fallback_classifications"] / total)
            * 100,
            "other_percentage": (self.metrics["other_assignments"] / total) * 100,
        }


async def main():
    """Demonstrate production-ready memory system."""
    print("=" * 80)
    print("Production-Ready Memory System with Smart Classification")
    print("=" * 80)

    # Initialize system with MockLLM for demonstration
    system = SmartMemorySystem(
        llm=None,  # Will use MockLLM for demo
        confidence_threshold=0.5,
        expansion_threshold=3,
    )

    # Simulate real-world memory stream
    memory_stream = [
        # Simple memories - should use fast classification
        "My name is Alice Johnson",
        "I work at Amazon",
        "I prefer Python",
        # Complex memories - should trigger LLM
        "The intersection of my background in neuroscience and current work in AI has led me to explore consciousness in machines",
        "During yesterday's standup, we discussed the microservices migration timeline and its impact on Q1 deliverables",
        # Edge cases - should go to 'other' and use LLM
        "I collect vintage synthesizers from the 1980s",
        "My sourdough starter is named Fred",
        "I'm learning to play the didgeridoo",
        # More normal memories
        "I graduated from Stanford in 2015",
        "My favorite IDE is VS Code",
        # More edge cases to trigger expansion
        "I restore old pinball machines",
        "I practice falconry on weekends",
        "I'm building a tiny house",
    ]

    print("\n1. Processing Memory Stream:")
    print("-" * 60)

    results = await system.process_batch(memory_stream)

    for result in results["results"]:
        is_other = "other" in result["path"]
        marker = "⚠️" if is_other else "✓"
        method_icon = "🤖" if "llm" in result["method"] else "⚡"

        print(f"\n{marker} {method_icon} '{result['content']}'")
        print(f"   Path: {result['path']}")
        print(f"   Confidence: {result['confidence']:.2f}")
        print(f"   Method: {result['method']}")

    print("\n" + "=" * 80)
    print("2. System Metrics:")
    print("-" * 60)

    metrics = results["metrics"]
    print(
        f"Direct classifications:   {metrics['direct_classifications']} ({metrics.get('direct_percentage', 0):.1f}%)"
    )
    print(
        f"Fallback classifications: {metrics['fallback_classifications']} ({metrics.get('fallback_percentage', 0):.1f}%)"
    )
    print(
        f"'Other' assignments:      {metrics['other_assignments']} ({metrics.get('other_percentage', 0):.1f}%)"
    )
    print(f"Expansions triggered:     {metrics['expansions_triggered']}")

    print("\n" + "=" * 80)
    print("3. Taxonomy State:")
    print("-" * 60)

    stats = system.taxonomy.get_statistics()
    print(f"Total paths: {stats['total_paths']}")
    print(f"Dynamic paths: {stats['dynamic_paths']}")
    print(f"Unclassified items: {stats['unclassified_items']}")

    print("\n" + "=" * 80)
    print("4. Key Insights:")
    print("-" * 60)
    print("• System uses LLM for all classifications (production-ready)")
    print("• No hardcoded logic - all decisions made by LLM reasoning")
    print("• Fallback system routes low-confidence items to 'other' categories")
    print("• 'Other' categories accumulate items for future taxonomy expansion")
    print("• Metrics help monitor classification performance")
    print("• MockLLM used for demo - replace with real LLM in production")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
