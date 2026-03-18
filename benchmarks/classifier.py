"""
Benchmark script for IntelligentClassifier performance testing.

This script measures the performance of:
1. Remember (classification) - storing memories with semantic classification
2. Recall (retrieval) - searching and retrieving memories

Uses LiteLLM for multi-provider support (OpenAI, Anthropic, Google, Ollama, vLLM, etc.)

Usage:
    # OpenAI (default)
    export OPENAI_API_KEY=your-api-key-here
    python benchmarks/classifier.py

    # Anthropic Claude - Haiku 4.5 (fast, cheap, supports prompt caching)
    export ANTHROPIC_API_KEY=your-api-key-here
    python benchmarks/classifier.py --model claude-haiku-4-5

    # Anthropic Claude - Sonnet 4.6 (balanced)
    python benchmarks/classifier.py --model claude-sonnet-4-6

    # Anthropic Claude 3 Haiku (legacy, cheapest - $0.25/$1.25 per MTok)
    python benchmarks/classifier.py --model claude-3-haiku-20240307

    # Google Gemini
    export GEMINI_API_KEY=your-api-key-here
    python benchmarks/classifier.py --model gemini/gemini-1.5-flash

    # Ollama (local, free)
    python benchmarks/classifier.py --model ollama/llama3.2

    # vLLM or OpenAI-compatible endpoint
    python examples/benchmark_classifier.py --model openai/my-model --base-url http://localhost:8000/v1

Options:
    --model MODEL       LiteLLM model identifier (default: gpt-4o-mini)
    --base-url URL      Custom base URL for OpenAI-compatible endpoints
    --classifier TYPE   Classifier type: 'intelligent' (default) or 'semantic'
    --num-cases N       Number of test cases to run (default: all)
    --verbose           Show detailed output for each operation
    --skip-remember     Skip remember benchmarks
    --skip-recall       Skip recall benchmarks
"""

import argparse
import asyncio
import logging
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

from memoir.llm import LiteLLMWrapper


@dataclass
class TimingResult:
    """Stores timing information for a single operation."""

    operation: str
    input_text: str
    duration_ms: float
    success: bool
    result_path: Optional[str] = None
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark results."""

    operation_type: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    std_dev_ms: float
    p95_ms: float
    p99_ms: float
    timings: list[TimingResult] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"  {self.operation_type.upper()} BENCHMARK RESULTS",
            f"{'='*60}",
            f"  Total operations:     {self.total_operations}",
            f"  Successful:           {self.successful_operations}",
            f"  Failed:               {self.failed_operations}",
            f"  Success rate:         {self.successful_operations/self.total_operations*100:.1f}%",
            "",
            "  Latency Statistics (ms):",
            f"    Min:                {self.min_ms:.2f}",
            f"    Max:                {self.max_ms:.2f}",
            f"    Mean:               {self.mean_ms:.2f}",
            f"    Median:             {self.median_ms:.2f}",
            f"    Std Dev:            {self.std_dev_ms:.2f}",
            f"    P95:                {self.p95_ms:.2f}",
            f"    P99:                {self.p99_ms:.2f}",
            f"{'='*60}",
        ]
        return "\n".join(lines)


def get_llm(
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    enable_prompt_cache: bool = True,
):
    """
    Get LLM instance using LiteLLM for multi-provider support.

    Supported model formats:
        - OpenAI: gpt-4o-mini, gpt-4o, gpt-3.5-turbo
        - Anthropic: claude-3-5-sonnet-20241022, claude-3-opus-20240229
        - Google: gemini/gemini-1.5-flash, gemini/gemini-1.5-pro
        - Ollama: ollama/llama3.2, ollama/mistral
        - vLLM: openai/model-name (with --base-url)
        - Azure: azure/deployment-name
        - And 100+ more providers...

    Prompt caching is automatically enabled for supported Anthropic models,
    reducing costs by up to 90% on repeated taxonomy/instruction tokens.

    See https://docs.litellm.ai/docs/providers for full list.
    """
    # Check for required API keys based on model
    model_lower = model.lower()

    # Auto-add provider prefix if missing (LiteLLM requires provider/model format)
    if model_lower.startswith("claude") and not model_lower.startswith("anthropic/"):
        model = f"anthropic/{model}"
        model_lower = model.lower()

    if model_lower.startswith("anthropic/") or model_lower.startswith("claude"):
        if not os.getenv("ANTHROPIC_API_KEY"):
            print(
                "Error: ANTHROPIC_API_KEY environment variable is required for Claude models"
            )
            print("Set your API key: export ANTHROPIC_API_KEY=your-api-key-here")
            sys.exit(1)
    elif model_lower.startswith("gemini"):
        if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
            print(
                "Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required for Gemini models"
            )
            print("Set your API key: export GEMINI_API_KEY=your-api-key-here")
            sys.exit(1)
    elif model_lower.startswith("ollama"):
        # Ollama runs locally, no API key needed
        pass
    elif base_url:
        # Custom endpoint, API key may not be needed
        pass
    else:
        # Default to OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            print(
                "Error: OPENAI_API_KEY environment variable is required for OpenAI models"
            )
            print("Set your API key: export OPENAI_API_KEY=your-api-key-here")
            print("\nOr use a different provider:")
            print("  --model claude-3-5-sonnet-20241022  (requires ANTHROPIC_API_KEY)")
            print("  --model gemini/gemini-1.5-flash     (requires GEMINI_API_KEY)")
            print("  --model ollama/llama3.2             (local, no API key)")
            sys.exit(1)

    try:
        llm = LiteLLMWrapper(
            model=model,
            temperature=0,
            max_tokens=500,
            base_url=base_url,
            enable_prompt_cache=enable_prompt_cache,
            debug_cache=True,  # Enable cache debugging for benchmarks
        )
        print(f"Using model: {model}")
        if base_url:
            print(f"Using base URL: {base_url}")
        if enable_prompt_cache and llm._supports_prompt_cache():
            print("Prompt caching: ENABLED (up to 90% cost savings on repeated tokens)")
        return llm
    except ImportError as e:
        print(f"Error: {e}")
        print("Install with: pip install litellm")
        sys.exit(1)


def calculate_percentile(data: list[float], percentile: float) -> float:
    """Calculate percentile of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100)
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return (
        sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
        if f != c
        else sorted_data[f]
    )


def create_benchmark_report(
    operation_type: str, timings: list[TimingResult]
) -> BenchmarkReport:
    """Create a benchmark report from timing results."""
    successful = [t for t in timings if t.success]
    durations = [t.duration_ms for t in successful]

    if not durations:
        return BenchmarkReport(
            operation_type=operation_type,
            total_operations=len(timings),
            successful_operations=0,
            failed_operations=len(timings),
            min_ms=0,
            max_ms=0,
            mean_ms=0,
            median_ms=0,
            std_dev_ms=0,
            p95_ms=0,
            p99_ms=0,
            timings=timings,
        )

    return BenchmarkReport(
        operation_type=operation_type,
        total_operations=len(timings),
        successful_operations=len(successful),
        failed_operations=len(timings) - len(successful),
        min_ms=min(durations),
        max_ms=max(durations),
        mean_ms=statistics.mean(durations),
        median_ms=statistics.median(durations),
        std_dev_ms=statistics.stdev(durations) if len(durations) > 1 else 0,
        p95_ms=calculate_percentile(durations, 95),
        p99_ms=calculate_percentile(durations, 99),
        timings=timings,
    )


def load_test_data() -> tuple[list[str], list[str]]:
    """Load test data from JSON files."""
    import json
    from pathlib import Path

    data_dir = Path(__file__).parent / "data"

    with open(data_dir / "remember_test_data.json") as f:
        remember_data = json.load(f)

    with open(data_dir / "recall_test_queries.json") as f:
        recall_queries = json.load(f)

    return remember_data, recall_queries


REMEMBER_TEST_DATA, RECALL_TEST_QUERIES = load_test_data()


async def benchmark_remember(
    memory_manager,
    classifier,  # noqa: ARG001
    test_data: list[str],
    namespace: str,
    verbose: bool = False,
) -> BenchmarkReport:
    """Benchmark the remember (store_memory) operation.

    This uses memory_manager.store_memory() which includes classification,
    so memories are stored and available for recall benchmark.
    """
    print(f"\nBenchmarking REMEMBER operation ({len(test_data)} items)...")

    timings = []

    for _i, memory_text in enumerate(test_data):
        start_time = time.perf_counter()
        error = None
        result_path = None
        details = {}

        try:
            # Use store_memory which classifies AND stores in one operation
            result_path = await memory_manager.store_memory(
                content=memory_text,
                namespace=namespace,
                metadata={"source": "benchmark"},
                auto_classify=True,
            )
            success = result_path is not None
            details = {
                "confidence": 0.95,  # store_memory doesn't return confidence
                "is_memory": True,
            }

        except Exception as e:
            error = str(e)
            success = False

        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000

        timing = TimingResult(
            operation="remember",
            input_text=(
                memory_text[:50] + "..." if len(memory_text) > 50 else memory_text
            ),
            duration_ms=duration_ms,
            success=success,
            result_path=result_path,
            error=error,
            details=details,
        )
        timings.append(timing)

        if verbose:
            status = "OK" if success else "FAIL"
            path_info = f" -> {result_path}" if result_path else ""
            conf_info = (
                f" ({details.get('confidence', 0):.0%})"
                if details.get("confidence")
                else ""
            )
            print(
                f"    [{status}] {duration_ms:>8.2f}ms - {timing.input_text}{path_info}{conf_info}"
            )

    return create_benchmark_report("remember (store)", timings)


async def evaluate_recall_quality(llm, query: str, memories: list[str]) -> dict:
    """
    Use LLM to evaluate if recalled memories answer the query.

    Returns:
        dict with 'answers_query' (bool), 'confidence' (float 0-1), and 'answer' (str)
    """
    if not memories:
        return {
            "answers_query": False,
            "confidence": 1.0,
            "answer": "No memories found",
        }

    memories_text = "\n".join(f"- {m[:200]}" for m in memories[:5])

    prompt = f"""Given these memories, answer the question. If you cannot answer, say "Cannot answer".

Question: "{query}"

Memories:
{memories_text}

Respond in this exact format:
ANSWER: <direct answer or "Cannot answer">
CONFIDENCE: <0.0 to 1.0>"""

    try:
        if hasattr(llm, "ainvoke"):
            response = await llm.ainvoke(prompt)
        else:
            response = llm.invoke(prompt)

        response_text = response.content.strip()

        # Parse response
        answer = ""
        confidence = 0.0

        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith("ANSWER:"):
                answer = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    confidence = 0.5

        answers_query = answer.lower() != "cannot answer" and len(answer) > 0

        return {
            "answers_query": answers_query,
            "confidence": confidence,
            "answer": answer,
        }

    except Exception as e:
        return {
            "answers_query": False,
            "confidence": 0.0,
            "answer": f"Error: {e}",
        }


async def benchmark_recall(
    memory_manager,  # noqa: ARG001
    search_engine,
    llm,
    test_queries: list[str],
    namespace: str,
    verbose: bool = False,
    limit: int = 5,
) -> BenchmarkReport:
    """Benchmark the recall (retrieval) operation with LLM quality evaluation."""
    print(f"\nBenchmarking RECALL operation ({len(test_queries)} queries)...")

    timings = []

    for query in test_queries:
        start_time = time.perf_counter()
        error = None
        result_path = None
        details = {}
        memories_content = []

        try:
            # Use the search engine directly
            search_start = time.perf_counter()
            results = await search_engine.search(
                query=query,
                namespace=namespace,
                limit=limit,
            )
            search_time_ms = (time.perf_counter() - search_start) * 1000

            if results and not results[0].metadata.get("is_timing_only"):
                result_path = results[0].path
                memories_content = [r.content for r in results if r.content]

                # Evaluate quality with LLM
                eval_start = time.perf_counter()
                eval_result = await evaluate_recall_quality(
                    llm, query, memories_content
                )
                eval_time_ms = (time.perf_counter() - eval_start) * 1000

                step_timings = results[0].metadata.get("step_timings", {})
                step_timings["search_total"] = (
                    search_time_ms / 1000
                )  # Convert to seconds
                step_timings["eval_quality"] = eval_time_ms / 1000  # Convert to seconds

                details = {
                    "num_results": len(results),
                    "top_result_content": (
                        results[0].content[:100] if results[0].content else None
                    ),
                    "step_timings": step_timings,
                    "answers_query": eval_result["answers_query"],
                    "eval_confidence": eval_result["confidence"],
                    "eval_answer": eval_result["answer"],
                }
                # Success = found results AND they answer the query
                success = eval_result["answers_query"]
            else:
                details = {
                    "num_results": 0,
                    "step_timings": (
                        results[0].metadata.get("step_timings", {}) if results else {}
                    ),
                    "answers_query": False,
                    "eval_confidence": 1.0,
                    "eval_answer": "Cannot answer",
                }
                success = False

        except Exception as e:
            error = str(e)
            success = False

        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000

        timing = TimingResult(
            operation="recall",
            input_text=query[:50] + "..." if len(query) > 50 else query,
            duration_ms=duration_ms,
            success=success,
            result_path=result_path,
            error=error,
            details=details,
        )
        timings.append(timing)

        if verbose:
            status = "OK" if success else "MISS"
            path_info = f" -> {result_path}" if result_path else ""
            num_results = details.get("num_results", 0)
            conf = details.get("eval_confidence", 0)
            results_info = (
                f" ({num_results} results, {conf:.0%} conf)" if num_results else ""
            )
            print(
                f"    [{status}] {duration_ms:>8.2f}ms - {timing.input_text}{path_info}{results_info}"
            )
            # Show retrieved memories and LLM answer
            if num_results > 0:
                print(
                    f"           Memories: {[m[:60] + '...' if len(m) > 60 else m for m in memories_content[:3]]}"
                )
                print(f"           Answer: {details.get('eval_answer', 'N/A')}")

    return create_benchmark_report("recall (retrieval)", timings)


async def run_benchmark(
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    num_cases: Optional[int] = None,
    verbose: bool = False,
    skip_recall: bool = False,
    classifier_type: str = "intelligent",
    enable_metadata_extraction: bool = False,
    recall_limit: int = 5,
):
    """Run the full benchmark suite."""
    from memoir import ProllyTreeMemoryStoreManager
    from memoir.classifier.intelligent import IntelligentClassifier
    from memoir.classifier.semantic import SemanticClassifier
    from memoir.search.intelligent import IntelligentSearchEngine
    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader
    from memoir.taxonomy.taxonomy import TaxonomyVersion

    classifier_name = classifier_type.upper()
    print("=" * 60)
    print(f"  MEMOIR {classifier_name} CLASSIFIER BENCHMARK")
    print("  (Powered by LiteLLM - supports 100+ LLM providers)")
    print("=" * 60)

    # Setup
    llm = get_llm(model, base_url=base_url)

    with tempfile.TemporaryDirectory() as temp_dir:
        prolly_path = os.path.join(temp_dir, "benchmark_store")

        print("\nInitializing components...")

        # Create storage
        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )

        # Initialize TaxonomyLoader - load from store (only init if not already present)
        print("  Initializing taxonomy from store...")
        taxonomy_loader = TaxonomyLoader(prolly_store)
        if not taxonomy_loader.has_taxonomy_in_store():
            result = taxonomy_loader.init_store(include_builtin=True)
            print(
                f"  Taxonomy initialized: {result['loaded']['examples']} examples, "
                f"{result['loaded']['descriptions']} descriptions, "
                f"{result['loaded']['preset']} presets"
            )
        else:
            print("  Taxonomy already in store, skipping initialization")

        # Create classifier based on type
        if classifier_type == "semantic":
            classifier = SemanticClassifier(
                llm=llm,
            )
            print("  Using SemanticClassifier (pattern-based + LLM fallback)")
        else:
            classifier = IntelligentClassifier(
                llm=llm,
                taxonomy_version=TaxonomyVersion.GENERAL,
                confidence_thresholds={
                    "high": 0.8,
                    "medium": 0.5,
                    "low": 0.0,
                },
                min_items_for_expansion=3,
                suppress_path_warnings=True,
                enable_metadata_extraction=enable_metadata_extraction,
                taxonomy_loader=taxonomy_loader,
            )
            extraction_mode = (
                "with metadata" if enable_metadata_extraction else "fast mode"
            )
            print(f"  Using IntelligentClassifier ({extraction_mode})")

        # Create search engine
        search_engine = IntelligentSearchEngine(
            llm=llm,
            store=prolly_store,
            taxonomy_loader=taxonomy_loader,
        )

        # Create memory manager
        memory_manager = ProllyTreeMemoryStoreManager(
            prolly_store=prolly_store,
            classifier=classifier,
            search_engine=search_engine,
            enable_versioning=True,
        )

        user_id = "benchmark_user"
        reports = []

        # Limit test data if num_cases is specified
        remember_data = (
            REMEMBER_TEST_DATA[:num_cases] if num_cases else REMEMBER_TEST_DATA
        )
        recall_queries = (
            RECALL_TEST_QUERIES[:num_cases] if num_cases else RECALL_TEST_QUERIES
        )

        if num_cases:
            print(f"Limiting to {num_cases} test case(s)")

        # Run remember benchmark (this also stores memories for recall)
        remember_report = await benchmark_remember(
            memory_manager=memory_manager,
            classifier=classifier,
            test_data=remember_data,
            namespace=user_id,
            verbose=verbose,
        )
        reports.append(remember_report)
        print(remember_report)

        # Run recall benchmark
        if not skip_recall:
            recall_report = await benchmark_recall(
                memory_manager=memory_manager,
                search_engine=search_engine,
                llm=llm,
                test_queries=recall_queries,
                namespace=user_id,
                verbose=verbose,
                limit=recall_limit,
            )
            reports.append(recall_report)
            print(recall_report)

        # Summary
        print("\n" + "=" * 60)
        print("  BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"  Classifier:      {classifier_type}")
        print(f"  Model:           {model}")

        for report in reports:
            print(f"\n  {report.operation_type}:")
            print(f"    Mean latency:  {report.mean_ms:.2f}ms")
            print(f"    P95 latency:   {report.p95_ms:.2f}ms")
            print(
                f"    Success rate:  {report.successful_operations/report.total_operations*100:.1f}%"
            )

        print("\n" + "=" * 60)

        # Detailed timing breakdown for recall (if available)
        if not skip_recall and recall_report.timings:
            print("\n  RECALL STEP BREAKDOWN (from step_timings):")
            step_times = {
                "step1": [],
                "step2": [],
                "step3": [],
                "search": [],
                "eval": [],
            }

            for timing in recall_report.timings:
                if timing.success and "step_timings" in timing.details:
                    st = timing.details["step_timings"]
                    if st.get("step1_path_discovery"):
                        step_times["step1"].append(st["step1_path_discovery"] * 1000)
                    if st.get("step2_path_selection"):
                        step_times["step2"].append(st["step2_path_selection"] * 1000)
                    if st.get("step3_memory_retrieval"):
                        step_times["step3"].append(st["step3_memory_retrieval"] * 1000)
                    if st.get("search_total"):
                        step_times["search"].append(st["search_total"] * 1000)
                    if st.get("eval_quality"):
                        step_times["eval"].append(st["eval_quality"] * 1000)

            step_names = {
                "step1": "Path Discovery",
                "step2": "Path Selection (LLM)",
                "step3": "Memory Retrieval",
                "search": "Search Total",
                "eval": "Quality Eval (LLM)",
            }

            for step, times in step_times.items():
                if times:
                    mean_time = statistics.mean(times)
                    print(f"    {step_names[step]:30s} Mean: {mean_time:>8.2f}ms")

            print("=" * 60)

        # Display prompt cache statistics (for Anthropic models)
        if hasattr(llm, "get_cache_stats") and llm._supports_prompt_cache():
            cache_stats = llm.get_cache_stats()
            if cache_stats["total_requests"] > 0:
                print("\n  PROMPT CACHE STATISTICS (Anthropic)")
                print("=" * 60)
                print(f"  Total requests:              {cache_stats['total_requests']}")
                print(
                    f"  Cached requests:             {cache_stats['cached_requests']}"
                )
                print(
                    f"  Cache hit rate:              {cache_stats['cache_hit_rate']*100:.1f}%"
                )
                print(
                    f"  Cache creation tokens:       {cache_stats['cache_creation_input_tokens']:,}"
                )
                print(
                    f"  Cache read tokens:           {cache_stats['cache_read_input_tokens']:,}"
                )
                print(
                    f"  Estimated token savings:     {cache_stats['estimated_token_savings']:,} tokens (90% discount)"
                )
                print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark IntelligentClassifier performance (using LiteLLM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # OpenAI (default)
  python benchmark_classifier.py --model gpt-4o-mini

  # Anthropic Claude Haiku 4.5 (fast, cheap, prompt caching)
  python benchmark_classifier.py --model claude-haiku-4-5

  # Anthropic Claude Sonnet 4.6 (balanced)
  python benchmark_classifier.py --model claude-sonnet-4-6

  # Anthropic Claude 3 Haiku (legacy, cheapest)
  python benchmark_classifier.py --model claude-3-haiku-20240307

  # Google Gemini
  python benchmark_classifier.py --model gemini/gemini-1.5-flash

  # Ollama (local, free)
  python benchmark_classifier.py --model ollama/llama3.2

  # vLLM or custom OpenAI-compatible endpoint
  python benchmark_classifier.py --model openai/my-model --base-url http://localhost:8000/v1

Supported providers: OpenAI, Anthropic, Google, Ollama, Azure, AWS Bedrock, vLLM, and 100+ more.
See https://docs.litellm.ai/docs/providers for full list.
        """,
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="LiteLLM model identifier (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Custom base URL for OpenAI-compatible endpoints (vLLM, Ollama API, etc.)",
    )
    parser.add_argument(
        "--num-cases",
        type=int,
        default=None,
        help="Number of test cases to run (default: all). Use small numbers like 1-3 for quick tests.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output for each operation",
    )
    parser.add_argument(
        "--skip-recall",
        action="store_true",
        help="Skip recall benchmarks",
    )
    parser.add_argument(
        "--classifier",
        type=str,
        choices=["intelligent", "semantic"],
        default="intelligent",
        help="Classifier type to benchmark: 'intelligent' (default) or 'semantic'",
    )
    parser.add_argument(
        "--metadata-extraction",
        action="store_true",
        help="Enable profile/timeline/location extraction (slower but richer output)",
    )
    parser.add_argument(
        "--recall-limit",
        type=int,
        default=5,
        help="Number of memories to retrieve per recall query (default: 5)",
    )

    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
        )
        # Enable memoir module logging at INFO level (use DEBUG for very verbose output)
        logging.getLogger("memoir").setLevel(logging.INFO)
        # Suppress noisy LiteLLM debug output
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        logging.getLogger("litellm").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    else:
        logging.basicConfig(level=logging.WARNING)

    asyncio.run(
        run_benchmark(
            model=args.model,
            base_url=args.base_url,
            num_cases=args.num_cases,
            verbose=args.verbose,
            skip_recall=args.skip_recall,
            classifier_type=args.classifier,
            enable_metadata_extraction=args.metadata_extraction,
            recall_limit=args.recall_limit,
        )
    )


if __name__ == "__main__":
    main()
