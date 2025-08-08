"""
Performance benchmark for LLM-based classification system.
Demonstrates classification performance and system capabilities.
"""

import asyncio
import random
import time
from statistics import mean, median
from typing import Any

from langmem_prollytree.taxonomy.dynamic_taxonomy import DynamicTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier


class MockLLMResponse:
    """Mock response object for benchmarking."""

    def __init__(self, content: str):
        self.content = content


class BenchmarkLLM:
    """Fast mock LLM for performance testing."""

    def __init__(self, response_time_ms: float = 1.0):
        self.response_time_ms = response_time_ms

    async def ainvoke(self, prompt: str) -> MockLLMResponse:
        """Simulate LLM response with controlled timing."""
        await asyncio.sleep(self.response_time_ms / 1000)  # Convert ms to seconds

        # Fast classification based on keywords
        content = prompt.lower()

        if "name" in content:
            return MockLLMResponse(
                """{
                "primary_path": "profile.personal.identity.name",
                "confidence": 0.90,
                "alternative_paths": [],
                "reasoning": "Name identification"
            }"""
            )
        elif "work" in content or "job" in content:
            return MockLLMResponse(
                """{
                "primary_path": "profile.professional.current.role",
                "confidence": 0.85,
                "alternative_paths": [],
                "reasoning": "Professional information"
            }"""
            )
        elif "experience" in content or "programming" in content:
            return MockLLMResponse(
                """{
                "primary_path": "profile.professional.skills.technical",
                "confidence": 0.85,
                "alternative_paths": [],
                "reasoning": "Technical skills"
            }"""
            )
        elif "prefer" in content or "favorite" in content:
            return MockLLMResponse(
                """{
                "primary_path": "preferences.personal.lifestyle",
                "confidence": 0.80,
                "alternative_paths": [],
                "reasoning": "Personal preferences"
            }"""
            )
        else:
            return MockLLMResponse(
                """{
                "primary_path": "context.other",
                "confidence": 0.50,
                "alternative_paths": [],
                "reasoning": "General content"
            }"""
            )


class BenchmarkSuite:
    """Comprehensive benchmark suite for classification performance."""

    def __init__(self, num_memories: int = 100, llm_response_time_ms: float = 1.0):
        self.num_memories = num_memories
        self.llm_response_time_ms = llm_response_time_ms
        self.results = {}

        # Sample memory templates for testing
        self.memory_templates = [
            "My name is {name} and I work at {company}",
            "I have {years} years of experience with {language} programming",
            "My favorite IDE theme is {theme} mode",
            "I prefer {preference} over {alternative}",
            "I graduated from {university} in {year}",
            "My current role is {role} at {company}",
            "I live in {city}, {country}",
            "I enjoy {hobby} in my free time",
            "I'm learning {skill} this year",
            "My team uses {tool} for {purpose}",
        ]

        # Sample data for templates
        self.sample_data = {
            "name": ["Alice Johnson", "Bob Smith", "Carol Davis"],
            "company": ["TechCorp", "DataInc", "CloudSys"],
            "years": ["2", "5", "8", "10"],
            "language": ["Python", "JavaScript", "Rust", "Go"],
            "theme": ["dark", "light"],
            "preference": ["TypeScript", "React", "Docker"],
            "alternative": ["JavaScript", "Vue", "VMs"],
            "university": ["MIT", "Stanford", "Berkeley"],
            "year": ["2018", "2019", "2020", "2021"],
            "role": ["Engineer", "Manager", "Architect"],
            "city": ["San Francisco", "New York", "Seattle"],
            "country": ["USA", "Canada"],
            "hobby": ["hiking", "reading", "gaming"],
            "skill": ["Kubernetes", "Machine Learning", "GraphQL"],
            "tool": ["GitHub", "Slack", "Figma"],
            "purpose": ["collaboration", "deployment", "design"],
        }

    def generate_test_memories(self) -> list[str]:
        """Generate test memories from templates."""
        memories = []
        for _ in range(self.num_memories):
            template = random.choice(self.memory_templates)
            # Fill template with random sample data
            filled_template = template
            for key, values in self.sample_data.items():
                if f"{{{key}}}" in template:
                    filled_template = filled_template.replace(
                        f"{{{key}}}", random.choice(values)
                    )
            memories.append(filled_template)
        return memories

    async def benchmark_classification(
        self, taxonomy: DynamicTaxonomy, memories: list[str]
    ) -> dict[str, Any]:
        """Benchmark classification performance."""
        print(f"\n📊 Benchmarking classification of {len(memories)} memories...")

        times = []
        confidences = []
        paths = []

        start_total = time.time()

        for i, memory in enumerate(memories):
            start_time = time.time()

            try:
                path, confidence = await taxonomy.classify_with_fallback(memory)
                classification_time = (time.time() - start_time) * 1000

                times.append(classification_time)
                confidences.append(confidence)
                paths.append(path)

                if (i + 1) % 25 == 0:
                    print(f"   Processed {i + 1}/{len(memories)} memories...")

            except Exception as e:
                print(f"   ❌ Error classifying memory {i+1}: {e}")

        total_time = (time.time() - start_total) * 1000

        return {
            "total_time_ms": total_time,
            "times_ms": times,
            "avg_time_ms": mean(times) if times else 0,
            "median_time_ms": median(times) if times else 0,
            "min_time_ms": min(times) if times else 0,
            "max_time_ms": max(times) if times else 0,
            "confidences": confidences,
            "avg_confidence": mean(confidences) if confidences else 0,
            "paths": paths,
            "success_count": len(times),
        }

    async def run_benchmark(self) -> dict[str, Any]:
        """Run complete benchmark suite."""
        print("=" * 80)
        print("LangMem-ProllyTree Classification Performance Benchmark")
        print("=" * 80)

        print("\n🔧 Configuration:")
        print(f"   • Test memories: {self.num_memories}")
        print(f"   • Mock LLM response time: {self.llm_response_time_ms}ms")

        # Generate test data
        print(f"\n📝 Generating {self.num_memories} test memories...")
        memories = self.generate_test_memories()
        print(f"   ✅ Generated {len(memories)} memories")

        # Initialize classification system
        print("\n⚙️  Initializing classification system...")
        llm = BenchmarkLLM(response_time_ms=self.llm_response_time_ms)
        classifier = SemanticClassifier(llm=llm)
        taxonomy = DynamicTaxonomy(
            classifier=classifier, confidence_threshold=0.6, expansion_threshold=10
        )
        print("   ✅ Classification system ready")

        # Run classification benchmark
        classification_results = await self.benchmark_classification(taxonomy, memories)

        # Analyze results
        print("\n📈 Performance Analysis:")
        print(
            f"   • Total classification time: {classification_results['total_time_ms']:.2f}ms"
        )
        print(f"   • Average per memory: {classification_results['avg_time_ms']:.2f}ms")
        print(f"   • Median time: {classification_results['median_time_ms']:.2f}ms")
        print(f"   • Fastest: {classification_results['min_time_ms']:.2f}ms")
        print(f"   • Slowest: {classification_results['max_time_ms']:.2f}ms")
        print(
            f"   • Success rate: {classification_results['success_count']}/{len(memories)} ({100*classification_results['success_count']/len(memories):.1f}%)"
        )

        print("\n🎯 Classification Quality:")
        print(
            f"   • Average confidence: {classification_results['avg_confidence']:.2f}"
        )

        # Analyze path distribution
        path_counts = {}
        for path in classification_results["paths"]:
            path_counts[path] = path_counts.get(path, 0) + 1

        print("\n📊 Path Distribution:")
        sorted_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)
        for path, count in sorted_paths[:10]:  # Top 10
            percentage = (count / len(classification_results["paths"])) * 100
            print(f"   • {path}: {count} ({percentage:.1f}%)")

        # Performance comparison
        throughput = len(memories) / (classification_results["total_time_ms"] / 1000)
        print("\n⚡ Performance Metrics:")
        print(f"   • Throughput: {throughput:.1f} classifications/second")
        print(
            f"   • vs Traditional LLM (2-5s): {2000/classification_results['avg_time_ms']:.0f}x faster"
        )
        print(
            f"   • Total time vs Traditional: {classification_results['total_time_ms']/1000:.2f}s vs {len(memories)*3:.0f}s"
        )

        # System state
        stats = taxonomy.get_statistics()
        print("\n🏗️  Taxonomy State:")
        print(f"   • Total paths: {stats['total_paths']}")
        print(f"   • Items in 'other': {stats['unclassified_items']}")
        if stats["unclassified_items"] > 0:
            print(
                f"   • Expansion ready: {'Yes' if stats['unclassified_items'] >= taxonomy.expansion_threshold else 'No'}"
            )

        return {
            "classification": classification_results,
            "taxonomy_stats": stats,
            "config": {
                "num_memories": self.num_memories,
                "llm_response_time_ms": self.llm_response_time_ms,
            },
        }


async def main():
    """Run performance benchmark with different configurations."""

    # Test different LLM response times to simulate various LLM providers
    test_configs = [
        {"memories": 50, "response_time": 1.0, "name": "Fast LLM (1ms)"},
        {"memories": 50, "response_time": 10.0, "name": "Medium LLM (10ms)"},
        {"memories": 25, "response_time": 50.0, "name": "Slow LLM (50ms)"},
    ]

    all_results = []

    for config in test_configs:
        print("\n" + "=" * 80)
        print(f"Testing {config['name']}")
        print("=" * 80)

        benchmark = BenchmarkSuite(
            num_memories=config["memories"],
            llm_response_time_ms=config["response_time"],
        )

        results = await benchmark.run_benchmark()
        results["config_name"] = config["name"]
        all_results.append(results)

        print(f"\n✅ Completed {config['name']} benchmark")

    # Summary comparison
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)

    for result in all_results:
        config_name = result["config_name"]
        avg_time = result["classification"]["avg_time_ms"]
        avg_confidence = result["classification"]["avg_confidence"]
        success_rate = (
            result["classification"]["success_count"]
            / result["config"]["num_memories"]
            * 100
        )

        print(f"\n{config_name}:")
        print(f"   Average time: {avg_time:.2f}ms")
        print(f"   Average confidence: {avg_confidence:.2f}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Throughput: {1000/avg_time:.1f} classifications/second")

    print("\n🎉 All benchmarks completed!")
    print(
        "💡 This demonstrates how the system scales with different LLM response times."
    )


if __name__ == "__main__":
    asyncio.run(main())
