"""
Intelligent Classifier with LLM-based classification and dynamic expansion.
Handles memory-worthiness detection, confidence-based expansion, and classification decisions.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .iterative_taxonomy import (
    LLMExpansionStrategy,
    LLMIterativeTaxonomy,
)
from .taxonomy_presets import TaxonomyVersion
from .taxonomy_presets_simplified import SimplifiedTaxonomyPresets, TaxonomyVersion as SimplifiedTaxonomyVersion

logger = logging.getLogger(__name__)


class ClassificationAction(Enum):
    """Action to take with classification."""

    SKIP = "skip"  # Not memory-worthy
    CLASSIFY = "classify"  # Classify to existing path
    EXPAND = "expand"  # Expand taxonomy for better classification
    USE_PARENT = "use_parent"  # Use more generic parent category


class MemoryAction(Enum):
    """Action to take with memory storage."""

    SKIP = "skip"  # Not stored
    STORE = "store"  # Store as new memory
    REPLACE = "replace"  # Replace existing memory
    APPEND = "append"  # Append to existing memory
    MERGE = "merge"  # Merge with existing memory


class ClassificationConfidence(Enum):
    """Confidence levels for classification."""

    HIGH = "high"  # > 0.8
    MEDIUM = "medium"  # 0.6 - 0.8
    LOW = "low"  # < 0.6


@dataclass
class ClassificationResult:
    """Result of LLM classification."""

    is_memory: bool
    confidence: float
    confidence_level: ClassificationConfidence
    reasoning: str
    suggested_action: ClassificationAction
    path: Optional[str] = None  # Primary path (for backward compatibility)
    paths: Optional[list[str]] = None  # Multiple paths for multi-label classification
    suggested_expansion: Optional[str] = None  # For low confidence
    use_parent: bool = False  # For low confidence
    profile_updates: Optional[list[dict[str, str]]] = None  # Profile updates detected

    @property
    def all_paths(self) -> list[str]:
        """Get all classification paths (primary + additional)."""
        if self.paths:
            return self.paths
        elif self.path:
            return [self.path]
        else:
            return []


@dataclass
class MemoryProcessingResult:
    """Result of complete memory processing including storage."""

    classification: ClassificationResult
    memory_action: MemoryAction
    memory_path: Optional[str] = None
    previous_content: Optional[str] = None
    new_content: Optional[str] = None
    expanded_paths: list[str] = None
    success: bool = True
    storage_reasoning: str = ""


class IntelligentClassifier:
    """
    Intelligent classifier with LLM-based classification and dynamic taxonomy expansion.
    Handles memory-worthiness detection, confidence-based expansion decisions.
    """

    def __init__(
        self,
        llm: Any,
        memory_store: Optional[Any] = None,
        taxonomy_version: TaxonomyVersion = TaxonomyVersion.GENERAL,
        confidence_thresholds: Optional[dict] = None,
        expansion_strategy: LLMExpansionStrategy = LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_for_expansion: int = 3,
        profile_manager: Optional[Any] = None,
        suppress_path_warnings: bool = True,
    ):
        """
        Initialize the intelligent classifier.

        Args:
            llm: Language model for classification and decisions
            memory_store: Optional memory store for actual storage operations
            taxonomy_version: Taxonomy preset to use
            confidence_thresholds: Custom confidence thresholds
            expansion_strategy: Strategy for taxonomy expansion
            min_items_for_expansion: Minimum items before expansion
            profile_manager: Optional profile manager for handling profile updates
            suppress_path_warnings: Whether to suppress warnings for invalid LLM-suggested paths
        """
        self.llm = llm
        self.memory_store = memory_store
        self.profile_manager = profile_manager
        self.taxonomy_version = taxonomy_version
        self.suppress_path_warnings = suppress_path_warnings

        # Initialize with simplified taxonomy to reduce LLM prompt size
        simplified_presets = SimplifiedTaxonomyPresets()
        preset_paths = simplified_presets.PRESETS[SimplifiedTaxonomyVersion.SIMPLIFIED]

        # Create a simple taxonomy object that provides get_all_paths() method
        class PresetTaxonomy:
            def __init__(self, preset_paths):
                self.preset_paths = preset_paths
                self._all_paths = []
                for category, paths in preset_paths.items():
                    # Do NOT add single-level categories to valid paths
                    # Only add multi-level paths (2+ levels minimum)
                    for path in paths:
                        full_path = f"{category}.{path}"
                        self._all_paths.append(full_path)

            def get_all_paths(self):
                return sorted(self._all_paths)

            def is_valid_path(self, path):
                return path in self._all_paths

        self.taxonomy = PresetTaxonomy(preset_paths)

        # Also keep iterative taxonomy for expansion capabilities if needed
        self.iterative_taxonomy = LLMIterativeTaxonomy(
            taxonomy_version=taxonomy_version,
            llm=llm,
            expansion_strategy=expansion_strategy,
            min_items_threshold=min_items_for_expansion,
        )

        # Confidence thresholds
        self.thresholds = confidence_thresholds or {
            "high": 0.8,
            "medium": 0.6,
            "low": 0.0,
        }

        # Track pending expansions
        self.pending_expansions = {}

    def _get_confidence_level(self, confidence: float) -> ClassificationConfidence:
        """Determine confidence level from score."""
        if confidence >= self.thresholds["high"]:
            return ClassificationConfidence.HIGH
        elif confidence >= self.thresholds["medium"]:
            return ClassificationConfidence.MEDIUM
        else:
            return ClassificationConfidence.LOW

    async def classify_input(
        self,
        content: str,
        metadata: Optional[dict] = None,
        conversation_context: Optional[list[str]] = None,
    ) -> ClassificationResult:
        """
        Classify input using LLM to determine if it's memory-worthy and where to store it.

        Args:
            content: The content to classify
            metadata: Optional metadata about the content
            conversation_context: Optional list of previous conversation exchanges for context

        Returns:
            ClassificationResult with classification details
        """
        # Get current taxonomy paths
        all_paths = self.taxonomy.get_all_paths()

        # Build classification prompt
        prompt = self._build_classification_prompt(
            content, all_paths, metadata, conversation_context
        )

        try:
            # Call LLM for classification
            response = await self.llm.ainvoke(prompt)

            # Parse response
            result = self._parse_classification_response(response)

            # Add confidence level
            result.confidence_level = self._get_confidence_level(result.confidence)

            return result

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Return skip action on error
            return ClassificationResult(
                is_memory=False,
                path=None,
                confidence=0.0,
                confidence_level=ClassificationConfidence.LOW,
                reasoning=f"Classification failed: {e!s}",
                suggested_action=ClassificationAction.SKIP,
            )

    def _build_classification_prompt(
        self,
        content: str,
        paths: list[str],
        metadata: Optional[dict],
        conversation_context: Optional[list[str]] = None,
    ) -> str:
        """Build prompt for LLM classification."""
        # Get first-level categories for context
        first_level = [p for p in paths if "." not in p and p != "other"]

        # Inform LLM about user's configured thresholds for better decisions
        threshold_guidance = []
        if self.thresholds["low"] > 0.0:
            threshold_guidance.append(
                f"   - IMPORTANT: User requires minimum {self.thresholds['low']:.1f} confidence to store ANY memory"
            )
        if self.thresholds["low"] >= 0.5:
            threshold_guidance.append(
                f"   - BE SELECTIVE: Only store memories you're at least {self.thresholds['low']:.1f} confident about"
            )
        if self.thresholds["low"] >= 0.7:
            threshold_guidance.append(
                "   - VERY CONSERVATIVE: User wants only high-quality, well-classified memories"
            )

        prompt_parts = [
            "You are a memory classification system. Analyze the following input and determine:",
            "1. Is this information worth storing as a memory?",
            "   - Skip transient information (greetings, current time, weather forecasts)",
            "   - Skip very general conversations without specific personal details",
            "   - Store personal preferences, facts, skills, relationships, goals, experiences",
        ]

        if threshold_guidance:
            prompt_parts.extend(threshold_guidance)

        prompt_parts.extend(
            [
                "",
                "2. If yes, which taxonomy path best fits this content?",
                "3. What is your confidence in this classification (0.0 to 1.0)?",
                f"   - User's minimum threshold: {self.thresholds['low']:.1f} (below this = not stored)",
                f"   - Medium confidence threshold: {self.thresholds['medium']:.1f}",
                f"   - High confidence threshold: {self.thresholds['high']:.1f}",
                "   - Only suggest storage if you meet the user's minimum threshold",
                "",
                "Confidence scoring guidelines:",
                "   - 0.9-1.0: Perfect fit, exact match to taxonomy path and clear content",
                "   - 0.7-0.8: Good fit, clearly belongs in this category",
                "   - 0.5-0.6: Moderate fit, somewhat belongs but could fit elsewhere",
                "   - 0.3-0.4: Poor fit, content is vague or path is not ideal",
                "   - 0.0-0.2: Very poor fit, should probably not be stored",
                "",
                f"Content to analyze (from [SELF]): {content}",
            ]
        )

        # Always clarify that content is from [SELF] perspective
        prompt_parts.extend(
            [
                "",
                "IMPORTANT: The content above is from [SELF] - classify based on their personal perspective/experience.",
            ]
        )

        if conversation_context:
            prompt_parts.extend(
                [
                    "",
                    "Previous conversation context (ONLY for understanding, DO NOT classify based on this):",
                    "Speaker Attribution Guide:",
                    "  [SELF] = The person whose memory you're classifying speaking",
                    "  [OTHER] = Someone else speaking to them",
                    "",
                ]
            )
            for i, prev_exchange in enumerate(conversation_context, 1):
                prompt_parts.append(f"  {i}. {prev_exchange}")

        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata)}")

        prompt_parts.extend(
            [
                "",
                "Available top-level categories:",
            ]
        )

        for category in sorted(first_level):
            prompt_parts.append(f"  - {category}")

        # Show ALL available paths to LLM for complete taxonomy coverage
        # NOTE: This approach works for current taxonomy size (~1000 paths)
        # Future scaling: May need chunking/filtering if taxonomy grows to 5K+ paths or hits LLM context limits
        all_non_other_paths = [p for p in paths if not p.endswith(".other")]
        if all_non_other_paths:
            prompt_parts.extend(
                [
                    "",
                    f"Complete taxonomy hierarchy ({len(all_non_other_paths)} available paths):",
                    "",
                ]
            )

            # Show ALL paths - no sampling to avoid missing critical paths like routine.morning or tools.ides
            for path in sorted(all_non_other_paths):
                prompt_parts.append(f"  {path}")

        prompt_parts.extend(
            [
                "",
                "Classification guidelines:",
                "- MANDATORY: Use MINIMUM 2 levels, preferably 3-4 levels in taxonomy paths",
                "- FORBIDDEN: Single-level paths like 'preferences', 'relationships', 'topics', 'goals' etc.",
                "- ALWAYS use SPECIFIC, DEEP paths from the taxonomy - NEVER use just top-level categories",
                "- PREFER existing COMPLETE paths that exist EXACTLY in the full taxonomy above",
                "- Use the full hierarchical path with 3-4 levels (e.g., topics.health.mental_health NOT just 'topics')",
                "- If content doesn't fit existing paths well, you can suggest NEW categories but with proper depth",
                "- Examples of GOOD specific classifications:",
                "  * 'I love mental health advocacy' → topics.health.mental_health (NOT just 'topics')",
                "  * 'My friend Tom is great' → entity.people.mentioned.friends (NOT just 'relationships')",
                "  * 'I work as a teacher' → profile.professional.occupation (NOT just 'profile')",
                "  * 'I chose them for their inclusivity' → preferences.personal.values (NOT just 'preferences')",
                "  * 'We have a great friendship' → relationships.people.friends.close (NOT just 'relationships')",
                "  * 'I want to adopt kids' → goals.categories.personal.relationships (NOT just 'goals')",
                "- Use appropriate hierarchical depth (3-4 levels strongly recommended)",
                "- Follow natural conceptual progression: general → specific",
                "- Avoid stopping at intermediate levels - go to the most specific applicable path",
                "- Consider existing similar paths for consistency",
                "",
                "NEW TOP-LEVEL CATEGORY GUIDELINES:",
                "- Only suggest new top-level categories if existing ones truly don't fit",
                "- New categories should be broad, fundamental aspects of human experience",
                "- Format: new_category.subcategory.specific_aspect",
                "- Examples: entity.people.mentioned.friends, language.slang.expressions, topics.technology.artificial_intelligence",
                "",
                "CONTEXT USAGE GUIDELINES:",
                "- CLASSIFY ONLY the main content (what the person actually said)",
                "- The context (previous conversation) is ONLY for understanding - DO NOT extract information from it",
                "- The context typically contains other people's questions/comments that prompted the response",
                "- Example: Context: 'Friend: What do you like to do?' Content: 'I love playing guitar' → Classify 'I love playing guitar' NOT 'What do you like to do?'",
                "- If the content references the context ('Yes, I do'), use context to understand what they're agreeing to, but classify based on the implied meaning in their response",
                "",
                "MULTI-LABEL CLASSIFICATION (USE VERY SPARINGLY):",
                "- ONLY use multiple paths when content contains information that belongs to DIFFERENT TOP-LEVEL CATEGORIES",
                "- You can also suggest new top-level categories if content doesn't fit existing ones",
                "- Example: 'I'm a single parent looking to adopt' maps to:",
                "  * profile.living.arrangements (PROFILE category - single parent status)",
                "  * goals.categories.personal.relationships (GOALS category - adoption goal)",
                "- Example: 'Great job on the fundraiser, Alex! Cancer research is so important' maps to:",
                "  * entity.people.mentioned.friends (ENTITY category - person mentioned)",
                "  * topics.health.medical_conditions (TOPICS category - health topic discussed)",
                "- Example: 'My colleague John mentioned he loves machine learning' maps to:",
                "  * entity.people.mentioned.colleagues (ENTITY category - person mentioned)",
                "  * topics.technology.artificial_intelligence (TOPICS category - subject discussed)",
                "- DO NOT use multiple paths if both pieces of information belong to the SAME top-level category",
                "- Examples of SINGLE path (same top-level category):",
                "  * 'I work as a software engineer and enjoy coding' → profile.professional.occupation (both are PROFILE)",
                "  * 'I want to learn guitar and piano' → goals.categories.education.skills (both are GOALS)",
                "- Maximum 2 paths, and ONLY when they have different top-level categories",
                "- When in doubt, use SINGLE path classification",
                "",
                "PROFILE vs TOPIC CLASSIFICATION:",
                "- PROFILE paths are for definitive facts ABOUT the person (identity, demographics, job, etc.)",
                "- TOPIC paths are for discussions or interests the person talks about",
                "- Examples of PROFILE classification:",
                "  * 'I am transgender' → profile.personal.identity.gender.identity",
                "  * 'Caroline is a transgender woman' → profile.personal.identity.gender.identity",
                "  * 'Caroline works as a counselor' → profile.professional.current.title",
                "  * 'I live in San Francisco' → profile.living.current.address.city",
                "  * 'My name is Caroline' → profile.personal.identity.name.first",
                "- Examples of TOPIC classification:",
                "  * 'The transgender stories were inspiring' → topics.social_issues.community",
                "  * 'I love discussing mental health' → topics.health.mental_health",
                "  * 'LGBTQ rights are important' → topics.social_issues.equality",
                "- IMPORTANT: If content contains biographical facts about the person, use PROFILE paths",
                "- If content is about their interests/discussions/opinions, use TOPIC paths",
                "",
                "",
                "PROFILE UPDATE DETECTION:",
                "- ALWAYS check if the content contains information that would UPDATE a user's PROFILE",
                "- Profile updates are DEFINITIVE facts about the user that replace previous information",
                "- Examples of profile updates:",
                "  * 'I'm 25 years old' → profile.personal.demographics.age.current",
                "  * 'I work at Google as a software engineer' → profile.professional.current.company + profile.professional.current.title",
                "  * 'I live in San Francisco' → profile.living.current.address.city",
                "  * 'I graduated from Stanford in 2020' → profile.professional.education.college.name + profile.professional.education.college.graduation_year",
                "  * 'I'm married to Sarah' → profile.personal.demographics.marital_status + profile.relationships.romantic.partner.name",
                "  * 'My salary is $150k' → profile.finance.income.primary.amount",
                "- If NO profile updates: return 'no_profile_update'",
                "- If profile updates exist: list them with path and new value",
                "",
                "Respond in JSON format:",
                "{",
                '  "is_memory": true/false,',
                '  "paths": ["primary.path.here", "secondary.path.here"] or ["single.path"] or null,',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "explanation of decision and path choices",',
                '  "profile_updates": "no_profile_update" or [{"path": "profile.path.here", "value": "new value"}]',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_classification_response(self, response: Any) -> ClassificationResult:
        """Parse LLM classification response."""
        try:
            # Handle different response types
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            # Try to parse as JSON
            # Extract JSON from response if wrapped in other text
            import re

            # First try to find complete JSON with proper bracket matching
            def extract_json(text):
                # Find the first opening brace
                start_idx = text.find('{')
                if start_idx == -1:
                    return None
                
                # Count braces to find the matching closing brace
                brace_count = 0
                for i in range(start_idx, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            return text[start_idx:i+1]
                return None

            json_str = extract_json(content)
            if json_str:
                data = json.loads(json_str)

                # Debug logging to see what we're getting
                logger.info(f"Parsed LLM response: {data}")
            else:
                # Fallback parsing - log the content that failed to parse
                logger.warning(
                    f"Failed to parse JSON from LLM response: {content[:200]}..."
                )
                data = {
                    "is_memory": False,
                    "path": None,
                    "confidence": 0.0,
                    "reasoning": "Failed to parse response",
                }

            # Handle both single path (backward compatibility) and multiple paths
            suggested_paths = data.get("paths")
            suggested_path = data.get("path")  # For backward compatibility

            # Normalize to list format
            if suggested_paths:
                paths_to_validate = suggested_paths
            elif suggested_path:
                paths_to_validate = [suggested_path]
            else:
                paths_to_validate = []

            # Validate that all suggested paths exist in taxonomy
            all_paths = self.taxonomy.get_all_paths()
            validated_paths = []

            # Existing top-level categories
            existing_top_level = {
                p.split(".")[0]
                for p in all_paths
                if "." in p
                or p
                in [
                    "profile",
                    "preferences",
                    "experience",
                    "context",
                    "knowledge",
                    "relationships",
                    "goals",
                    "behavior",
                ]
            }

            for path in paths_to_validate:
                if path and path in all_paths:
                    # Existing path - use as is
                    validated_paths.append(path)
                elif path:
                    path_parts = path.split(".")
                    top_level_category = path_parts[0]

                    # Check if this is a new top-level category
                    if (
                        top_level_category not in existing_top_level
                        and len(path_parts) >= 2
                    ):
                        # This appears to be a new top-level category suggestion
                        logger.info(f"LLM suggested new top-level category: {path}")
                        validated_paths.append(path)  # Accept new category paths
                    else:
                        # Try to find existing path or fallback
                        if not self.suppress_path_warnings:
                            logger.warning(
                                f"LLM suggested invalid path '{path}'. "
                                f"Available paths that contain relevant keywords: "
                                f"{[p for p in all_paths if any(word in p for word in path.split('.') if word != 'other')][:5]}"
                            )
                        # Try to find a close match or fall back to a more general path
                        found_valid = False
                        for i in range(len(path_parts), 0, -1):
                            partial_path = ".".join(path_parts[:i])
                            if partial_path in all_paths:
                                logger.info(f"Using valid parent path: {partial_path}")
                                validated_paths.append(partial_path)
                                found_valid = True
                                break

                        if not found_valid:
                            # Reject paths that are too shallow (single-level)
                            if len(path_parts) < 2:
                                logger.warning(
                                    f"Rejecting single-level path: {path}. Minimum 2 levels required."
                                )
                                continue

                            # Try to find a valid 2+ level path in the same domain
                            domain = path_parts[0]
                            valid_domain_paths = [
                                p
                                for p in all_paths
                                if p.startswith(f"{domain}.") and len(p.split(".")) >= 2
                            ]

                            if valid_domain_paths:
                                # Use a sensible default path in this domain as fallback
                                domain_defaults = {
                                    "preferences": "preferences.personal.interests",
                                    "relationships": "relationships.people.friends.close",
                                    "topics": "topics.social_issues.community",
                                    "goals": "goals.categories.personal.growth",
                                    "experience": "experience.memories.recent",
                                    "entity": "entity.people.mentioned.friends",
                                    "profile": "profile.personal.characteristics",
                                    "knowledge": "knowledge.facts.personal",
                                    "behavior": "behavior.patterns.social",
                                }

                                fallback_path = domain_defaults.get(
                                    domain, valid_domain_paths[0]
                                )
                                logger.info(
                                    f"Single-level '{domain}' converted to specific path: {fallback_path}"
                                )
                                validated_paths.append(fallback_path)
                            else:
                                logger.warning(
                                    f"No valid paths found for domain {domain}, skipping classification"
                                )

            # Enforce top-level category rule for multi-label classification
            if len(validated_paths) > 1:
                top_level_categories = [path.split(".")[0] for path in validated_paths]
                if len(set(top_level_categories)) == 1:
                    # All paths are from the same top-level category, keep only the first (most relevant)
                    logger.info(
                        f"Multiple paths from same top-level category {top_level_categories[0]}, keeping only primary path: {validated_paths[0]}"
                    )
                    validated_paths = [validated_paths[0]]
                elif len(set(top_level_categories)) > 2:
                    # More than 2 different top-level categories, keep only first 2
                    unique_categories = []
                    filtered_paths = []
                    for path in validated_paths:
                        category = path.split(".")[0]
                        if category not in unique_categories:
                            unique_categories.append(category)
                            filtered_paths.append(path)
                            if len(filtered_paths) == 2:
                                break
                    logger.info(
                        f"More than 2 top-level categories, keeping first 2: {filtered_paths}"
                    )
                    validated_paths = filtered_paths

            # Set primary path for backward compatibility
            primary_path = validated_paths[0] if validated_paths else None

            # Parse confidence and apply user threshold filtering
            confidence = float(data.get("confidence", 0.0))
            is_memory = data.get("is_memory", False)

            # Override is_memory if confidence doesn't meet user's threshold
            if is_memory and confidence < self.thresholds["low"]:
                is_memory = False
                reasoning_override = f"{data.get('reasoning', '')} | OVERRIDDEN: Confidence {confidence:.2f} < user threshold {self.thresholds['low']:.1f}"
            else:
                reasoning_override = data.get("reasoning", "")

            # Parse profile updates
            profile_updates = None
            profile_data = data.get("profile_updates")
            if (
                profile_data
                and profile_data != "no_profile_update"
                and isinstance(profile_data, list)
            ):
                profile_updates = profile_data
                logger.info(f"Detected profile updates: {profile_updates}")

            return ClassificationResult(
                is_memory=is_memory,
                path=primary_path if is_memory else None,
                paths=(
                    validated_paths if is_memory and len(validated_paths) > 0 else None
                ),
                confidence=confidence,
                confidence_level=ClassificationConfidence.LOW,  # Will be set later
                reasoning=reasoning_override,
                suggested_action=(
                    ClassificationAction.CLASSIFY
                    if is_memory
                    else ClassificationAction.SKIP
                ),
                profile_updates=profile_updates,
            )

        except Exception as e:
            logger.error(f"Failed to parse classification response: {e}")
            return ClassificationResult(
                is_memory=False,
                path=None,
                confidence=0.0,
                confidence_level=ClassificationConfidence.LOW,
                reasoning=f"Parse error: {e!s}",
                suggested_action=ClassificationAction.SKIP,
            )

    async def handle_low_confidence_classification(
        self,
        content: str,
        classification: ClassificationResult,
        metadata: Optional[dict] = None,
    ) -> ClassificationResult:
        """
        Handle low confidence classification by asking LLM to expand or use parent.

        Args:
            content: Original content
            classification: Initial classification result
            metadata: Optional metadata

        Returns:
            Updated classification result with expansion decision
        """
        if not classification.path:
            return classification

        # Build prompt for expansion decision
        prompt = self._build_expansion_decision_prompt(
            content, classification.path, classification.confidence, metadata
        )

        try:
            response = await self.llm.ainvoke(prompt)
            decision = self._parse_expansion_decision(response)

            if decision["action"] == "expand":
                # Trigger expansion for more specific categorization
                classification.suggested_expansion = decision.get("suggested_path")

                # Add to pending expansions
                parent_path = classification.path
                if parent_path not in self.pending_expansions:
                    self.pending_expansions[parent_path] = []
                self.pending_expansions[parent_path].append(
                    {
                        "content": content,
                        "metadata": metadata,
                        "suggested_expansion": decision.get("suggested_categories", []),
                    }
                )

                # If we have enough items, trigger expansion
                if (
                    len(self.pending_expansions[parent_path])
                    >= self.taxonomy.min_items_threshold
                ):
                    await self._trigger_expansion(parent_path)

            elif decision["action"] == "use_parent":
                # Use more generic category
                classification.use_parent = True
                parts = classification.path.split(".")
                if len(parts) > 1:
                    classification.path = ".".join(parts[:-1])
                    classification.confidence = decision.get("parent_confidence", 0.7)

            classification.reasoning += (
                f" | Expansion decision: {decision.get('reasoning', '')}"
            )

        except Exception as e:
            logger.error(f"Expansion decision failed: {e}")

        return classification

    def _build_expansion_decision_prompt(
        self, content: str, path: str, confidence: float, metadata: Optional[dict]
    ) -> str:
        """Build prompt for expansion decision."""
        prompt_parts = [
            f"The following content was classified to '{path}' with low confidence ({confidence:.2f}):",
            f"Content: {content}",
        ]

        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata)}")

        prompt_parts.extend(
            [
                "",
                "Should we:",
                "1. EXPAND to more specific subcategories (if content is very detailed/specialized)",
                "   - Use when content has specific technical details, rare skills, or unique activities",
                "   - IMPORTANT: Follow proper hierarchical depth progression:",
                "     * Add ONE intermediate level at a time (don't jump from 'knowledge' to 'knowledge.quantum.entanglement.protocols')",
                "     * Use general-to-specific progression: domain → area → specialty → technique",
                "     * Examples: 'knowledge.music' → 'knowledge.music.piano' → 'knowledge.music.piano.improvisation'",
                "   - Suggest 2-3 subcategory names that follow natural conceptual hierarchies",
                "",
                "2. USE_PARENT category (if content is too vague/general for current specificity)",
                "   - Use when content is general/broad and current path is too specific",
                "   - Move up one level in the taxonomy hierarchy for better fit",
                "",
                "3. KEEP current classification (if confidence is acceptable as-is)",
                "",
                f"Current path depth: {len(path.split('.')) if path else 0} levels",
                "Recommended max depth: 4 levels for most concepts",
                "",
                "Respond in JSON format:",
                "{",
                '  "action": "expand" | "use_parent" | "keep",',
                '  "reasoning": "explanation with depth justification",',
                '  "suggested_categories": ["intermediate_category", "specific_category"] (if expanding),',
                '  "parent_confidence": 0.0-1.0 (if using parent)',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_expansion_decision(self, response: Any) -> dict:
        """Parse expansion decision response."""
        try:
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.error(f"Failed to parse expansion decision: {e}")

        return {"action": "keep", "reasoning": "Parse error, keeping original"}

    async def _trigger_expansion(self, parent_path: str):
        """Trigger taxonomy expansion for a path."""
        try:
            # Use the iterative taxonomy's expansion
            result = await self.taxonomy.expand_subtree_with_llm(parent_path)

            if result.new_paths:
                logger.info(
                    f"Expanded {parent_path} with {len(result.new_paths)} new categories"
                )

                # Reclassify pending items
                if parent_path in self.pending_expansions:
                    for item in self.pending_expansions[parent_path]:
                        # Re-classify with new categories
                        await self.process_classification(
                            item["content"], item["metadata"]
                        )

                    # Clear pending items
                    del self.pending_expansions[parent_path]

        except Exception as e:
            logger.error(f"Expansion failed for {parent_path}: {e}")

    async def process_classification(
        self,
        content: str,
        metadata: Optional[dict] = None,
        conversation_context: Optional[list[str]] = None,
    ) -> ClassificationResult:
        """
        Main entry point for processing classification.

        Args:
            content: Content to classify
            metadata: Optional metadata
            conversation_context: Optional list of previous conversation exchanges for context

        Returns:
            ClassificationResult with classification details and recommended action
        """
        # Step 1: Classify the input
        classification = await self.classify_input(
            content, metadata, conversation_context
        )

        # Step 2: Check if it's memory-worthy
        if not classification.is_memory:
            return classification

        # Step 2.5: Validate suggested path exists in taxonomy
        if (
            classification.path
            and classification.path not in self.taxonomy.get_all_paths()
        ):
            # Path doesn't exist - mark for expansion but preserve original confidence
            # Only lower confidence if it was already very high (likely overconfident)
            if classification.confidence > 0.8:
                classification.confidence = min(classification.confidence, 0.75)
            classification.confidence_level = self._get_confidence_level(
                classification.confidence
            )
            classification.reasoning += (
                f" | Suggested path '{classification.path}' doesn't exist in taxonomy"
            )

        # Step 3: Handle based on confidence level
        if classification.confidence_level == ClassificationConfidence.LOW:
            # Handle low confidence with expansion decision
            classification = await self.handle_low_confidence_classification(
                content, classification, metadata
            )

            # Update suggested action based on expansion decision
            if classification.suggested_expansion:
                classification.suggested_action = ClassificationAction.EXPAND
            elif classification.use_parent:
                classification.suggested_action = ClassificationAction.USE_PARENT
            else:
                # For invalid paths or genuinely low confidence, suggest expansion if we have a path
                if (
                    classification.path
                    and classification.path not in self.taxonomy.get_all_paths()
                ):
                    classification.suggested_action = ClassificationAction.EXPAND
                    classification.reasoning += (
                        " | Invalid path suggests need for expansion"
                    )
                elif classification.confidence < self.thresholds["medium"]:
                    classification.suggested_action = ClassificationAction.SKIP
                    classification.reasoning += (
                        " | Confidence too low after expansion handling"
                    )

        # Step 4: Analyze and potentially improve hierarchical structure
        if classification.path and classification.is_memory:
            # Analyze hierarchical consistency
            analysis = self._analyze_hierarchical_consistency(classification.path)

            # Suggest better path if needed
            if analysis["suggested_improvements"]:
                improved_path = self._suggest_hierarchical_path(
                    content, classification.path
                )
                if improved_path != classification.path:
                    logger.info(
                        f"Suggested path improvement: {classification.path} → {improved_path}"
                    )
                    classification.path = improved_path
                    classification.reasoning += (
                        f" | Path improved for better hierarchy: {improved_path}"
                    )

            # Note: We skip iterative taxonomy tracking since we're using the full semantic taxonomy
            # The track_classification method runs domain consistency validation that may not match
            # our full taxonomy paths, causing spurious warnings

        return classification

    async def _generate_entity_storage_key(
        self, path: str, content: str, memory_data: dict
    ) -> str:
        """
        Generate entity-specific storage keys to avoid duplicate records for the same entities.

        For entity paths, we'll ask the LLM to identify the specific entity mentioned.
        For non-entity paths, return the original path.
        """
        if not path.startswith("entity."):
            return path

        # For entity paths, we'll use the LLM to identify the specific entity
        # This is more accurate than regex-based extraction
        try:
            entity_name = await self._get_entity_name_from_llm(content, path)
            if entity_name:
                # Clean and format the entity name for storage key
                clean_name = entity_name.lower().replace(" ", "_").replace("-", "_")
                return f"{path}#{clean_name}"
        except Exception as e:
            logger.warning(f"Failed to get entity name from LLM: {e}")

        # If no specific entity found or LLM failed, use original path
        return path

    async def _get_entity_name_from_llm(self, content: str, path: str) -> str:
        """
        Use the LLM to identify the specific entity mentioned in the content for the given path.
        This is more accurate than regex-based extraction.
        """
        # Determine what type of entity we're looking for based on the path
        entity_type = "entity"
        if "people.mentioned" in path:
            entity_type = "person name"
        elif "places." in path:
            entity_type = "place or location"
        elif "organizations." in path:
            entity_type = "organization or company name"
        elif "time." in path:
            entity_type = "time or date reference"
        elif "objects." in path:
            entity_type = "object or item"

        prompt = f"""Extract the most important {entity_type} mentioned in this text. Return only the name/identifier, nothing else.

Text: {content}
Path: {path}

Requirements:
- Return only the most relevant {entity_type} mentioned
- Use the exact name/phrase as it appears in the text
- If multiple {entity_type}s are mentioned, return the most prominent one
- Return just the name without quotes or explanation
- If no clear {entity_type} is found, return "none"

Examples:
- Text: "I went with my friend Sarah" → Sarah
- Text: "We visited New York City" → New York City
- Text: "I work at Google Inc" → Google Inc
- Text: "Yesterday was great" → yesterday"""

        try:
            response = await self.llm.ainvoke(prompt)
            entity_name = response.content.strip()

            # Clean up the response
            if entity_name.lower() in ["none", "null", "n/a", ""]:
                return None

            # Remove quotes if present
            entity_name = entity_name.strip("\"'")

            return entity_name if entity_name else None

        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}")
            return None

    async def process_memory_with_storage(
        self,
        content: str,
        metadata: Optional[dict] = None,
        conversation_context: Optional[list[str]] = None,
    ) -> MemoryProcessingResult:
        """
        Complete memory processing including classification and storage.

        Args:
            content: Content to process
            metadata: Optional metadata
            conversation_context: Optional list of previous conversation exchanges for context

        Returns:
            MemoryProcessingResult with classification and storage details
        """
        # Step 1: Classify the content
        classification = await self.process_classification(
            content, metadata, conversation_context
        )

        # Initialize result
        result = MemoryProcessingResult(
            classification=classification,
            memory_action=MemoryAction.SKIP,
            expanded_paths=[],
        )

        # Step 2: Handle based on classification
        if not classification.is_memory:
            result.storage_reasoning = "Content not memory-worthy"
            return result

        # Step 2.1: Check confidence threshold - CRITICAL for user-controlled aggressiveness
        if classification.confidence < self.thresholds["low"]:
            result.storage_reasoning = f"Confidence {classification.confidence:.2f} below threshold {self.thresholds['low']}"
            result.memory_action = MemoryAction.SKIP
            return result

        # Check if we have any paths to store under
        paths_to_store = classification.all_paths
        if not paths_to_store:
            result.storage_reasoning = "No classification paths provided"
            return result

        if not self.memory_store:
            result.storage_reasoning = "No memory store available"
            result.success = False
            return result

        # Step 2.5: Apply profile updates if detected
        if classification.profile_updates and self.profile_manager:
            try:
                await self.profile_manager.apply_profile_updates(
                    classification.profile_updates, metadata
                )
                logger.info(
                    f"Applied {len(classification.profile_updates)} profile updates"
                )
            except Exception as e:
                logger.error(f"Failed to apply profile updates: {e}")

        # Step 3: Handle memory storage under multiple paths
        namespace = ("memory", self.taxonomy_version.value)
        stored_paths = []
        storage_errors = []

        try:
            # Store simplified memory structure with only essential fields
            from datetime import datetime

            # Prepare memory data with conversation context embedded in raw_text
            formatted_content = content
            if conversation_context:
                # Include context directly in raw_text for clear association
                context_lines = []
                for ctx in conversation_context:
                    context_lines.append(f"Context: {ctx}")
                context_section = "\n".join(context_lines) + "\n"
                formatted_content = f"{context_section}{content}"

            memory_data = {
                "raw_text": formatted_content,  # Store raw conversation text with context
                "session_date": (
                    metadata.get("session_date", datetime.now().isoformat())
                    if metadata
                    else datetime.now().isoformat()
                ),  # Use actual session date from JSON
                "confidence": classification.confidence,
                "classification_paths": paths_to_store,  # Store all paths this content was classified under
            }

            # Keep conversation context in metadata for search/retrieval purposes
            if conversation_context:
                memory_data["conversation_context"] = conversation_context

            # Limit to maximum 2 paths for conservative multi-labeling
            paths_to_store = paths_to_store[:2]

            # Store under each classified path
            for path in paths_to_store:
                try:
                    # For entity paths, create more specific storage keys to avoid duplication
                    storage_key = await self._generate_entity_storage_key(
                        path, content, memory_data
                    )

                    # Check for existing content at this storage key
                    existing = self.memory_store.get(namespace, storage_key)

                    if existing is None:
                        # Store new memory
                        self.memory_store.put(namespace, storage_key, memory_data)
                        stored_paths.append(storage_key)
                    else:
                        # Handle existing memory - merge with new content
                        merged_memory = await self._merge_memories(
                            existing, memory_data, content, conversation_context
                        )
                        if merged_memory:
                            self.memory_store.put(namespace, storage_key, merged_memory)
                            stored_paths.append(storage_key)
                            logger.info(
                                f"Merged new content with existing memory at storage key {storage_key}"
                            )
                        else:
                            logger.info(
                                f"Conflict detected, skipping merge at storage key {storage_key}"
                            )

                except Exception as e:
                    storage_errors.append(f"Failed to store at {path}: {e}")
                    logger.error(f"Storage error for path {path}: {e}")

            if stored_paths:
                result.memory_action = MemoryAction.STORE
                result.memory_path = stored_paths[
                    0
                ]  # Primary path for backward compatibility
                result.new_content = content
                if len(stored_paths) == 1:
                    result.storage_reasoning = (
                        f"Stored raw memory at {stored_paths[0]} ({len(content)} chars)"
                    )
                else:
                    result.storage_reasoning = f"Stored raw memory at {len(stored_paths)} paths: {', '.join(stored_paths)} ({len(content)} chars)"
            else:
                result.memory_action = MemoryAction.SKIP
                result.storage_reasoning = (
                    f"Failed to store at any path. Errors: {'; '.join(storage_errors)}"
                )

        except Exception as e:
            result.success = False
            result.storage_reasoning = f"Storage failed: {e}"

        return result

    async def _merge_memories(
        self,
        existing_memory: dict,
        new_memory: dict,
        new_content: str,
        conversation_context: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """
        Intelligently merge new memory content with existing memory.

        Args:
            existing_memory: The existing memory data
            new_memory: The new memory data to merge
            new_content: The new raw content text
            conversation_context: Optional conversation context

        Returns:
            Merged memory dict if successful, None if conflict detected
        """
        try:
            # Get existing content
            existing_content = existing_memory.get("raw_text", "")

            # Check for conflicts using LLM
            conflict_check = await self._check_for_conflicts(
                existing_content, new_content
            )

            if conflict_check.get("has_conflict", False):
                logger.warning(
                    f"Conflict detected between existing and new content: {conflict_check.get('reasoning', 'Unknown conflict')}"
                )
                return None

            # No conflict - proceed with merge
            merged_memory = existing_memory.copy()

            # Append new content to existing with clear separation
            if existing_content and new_content:
                # Use the session_date directly - it's already formatted from the JSON
                timestamp = new_memory.get("session_date", "unknown time")

                # Create clear separation with context included in each entry
                new_entry_header = f"--- NEW ENTRY ({timestamp}) ---"

                # Include the conversation context for this new entry if available
                context_section = ""
                if conversation_context:
                    context_lines = []
                    for ctx in conversation_context:
                        context_lines.append(f"  Context: {ctx}")
                    context_section = "\n".join(context_lines) + "\n"

                merged_memory["raw_text"] = (
                    f"{existing_content}\n\n{new_entry_header}\n{context_section}{new_content}"
                )
            elif new_content:
                # For first entry, include context if available
                if conversation_context:
                    context_lines = []
                    for ctx in conversation_context:
                        context_lines.append(f"Context: {ctx}")
                    context_section = "\n".join(context_lines) + "\n"
                    merged_memory["raw_text"] = f"{context_section}{new_content}"
                else:
                    merged_memory["raw_text"] = new_content

            # Update session date to most recent
            merged_memory["session_date"] = new_memory.get(
                "session_date", merged_memory.get("session_date")
            )

            # Update confidence to higher of the two
            existing_confidence = existing_memory.get("confidence", 0.0)
            new_confidence = new_memory.get("confidence", 0.0)
            merged_memory["confidence"] = max(existing_confidence, new_confidence)

            # Keep conversation context for metadata but avoid duplication since it's now in raw_text
            # Store the most recent conversation context for search/retrieval purposes
            if conversation_context:
                merged_memory["conversation_context"] = conversation_context
            else:
                # Keep existing context if no new context provided
                merged_memory["conversation_context"] = existing_memory.get(
                    "conversation_context", []
                )

            # Update classification paths (union of both sets)
            existing_paths = set(existing_memory.get("classification_paths", []))
            new_paths = set(new_memory.get("classification_paths", []))
            merged_memory["classification_paths"] = list(existing_paths | new_paths)

            # Add merge metadata
            merged_memory["merge_count"] = existing_memory.get("merge_count", 0) + 1
            merged_memory["last_merged"] = new_memory.get("session_date")

            return merged_memory

        except Exception as e:
            logger.error(f"Error merging memories: {e}")
            return None

    async def _check_for_conflicts(
        self, existing_content: str, new_content: str
    ) -> dict:
        """
        Check if new content conflicts with existing content using LLM.

        Args:
            existing_content: The existing memory content
            new_content: The new content to check for conflicts

        Returns:
            Dict with conflict analysis
        """
        if not existing_content or not new_content:
            return {"has_conflict": False, "reasoning": "No content to compare"}

        prompt = f"""Analyze if these two pieces of information conflict with each other.

Existing information: {existing_content}
New information: {new_content}

Look for factual contradictions such as:
- Different values for the same attribute (age, location, job, etc.)
- Contradictory statements about preferences or facts
- Mutually exclusive statements

Do NOT consider these as conflicts:
- Additional details that expand on existing information
- Related but different aspects of the same topic
- Temporal progression (things changing over time)

Respond in JSON format:
{{
  "has_conflict": true/false,
  "reasoning": "explanation of the conflict or why no conflict exists"
}}"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = (
                response.content if hasattr(response, "content") else str(response)
            )

            # Parse JSON response
            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                return {
                    "has_conflict": False,
                    "reasoning": "Failed to parse conflict check",
                }

        except Exception as e:
            logger.error(f"Conflict check failed: {e}")
            return {"has_conflict": False, "reasoning": f"Conflict check error: {e}"}

    async def _create_semantic_summary(
        self, content: str, path: str, metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a concise, structured summary of the content based on taxonomy path.

        Args:
            content: Original content to summarize
            path: Taxonomy path for context-aware summarization
            metadata: Optional metadata for additional context

        Returns:
            Dict with 'summary' and 'structured_data' keys
        """
        # Build context-aware summarization prompt
        prompt_parts = [
            "Create a concise, structured summary of the following content.",
            "Extract key information and create both a brief summary and structured data.",
            "",
            f"Content: {content}",
            f"Classification path: {path}",
        ]

        if metadata:
            prompt_parts.append(f"Context: {json.dumps(metadata)}")

        # Add dynamic path-based context instead of hard-coded guidance
        prompt_parts.extend(
            [
                "",
                f"Context: This content is classified under '{path}' in our taxonomy.",
                "Extract the most relevant information for this classification category.",
                "Focus on specific, actionable details rather than general statements.",
                "",
                "Respond in JSON format:",
                "{",
                '  "summary": "1-2 sentence concise summary capturing the essence",',
                '  "structured_data": {',
                '    "key_field_1": "extracted_value_1",',
                '    "key_field_2": "extracted_value_2"',
                "    // Add relevant fields based on the taxonomy path",
                "  }",
                "}",
            ]
        )

        try:
            response = await self.llm.ainvoke("\n".join(prompt_parts))

            # Parse response
            if hasattr(response, "content"):
                content_str = response.content
            else:
                content_str = str(response)

            # Extract JSON from response
            import re

            json_match = re.search(r"\{.*\}", content_str, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                # Validate and clean up the result
                summary = result.get(
                    "summary", content[:200] + "..." if len(content) > 200 else content
                )
                structured_data = result.get("structured_data", {})

                return {"summary": summary, "structured_data": structured_data}
            else:
                logger.warning(
                    f"Failed to parse summarization response: {content_str[:200]}..."
                )
                # Fallback to simple truncation
                return {
                    "summary": content[:200] + "..." if len(content) > 200 else content,
                    "structured_data": {},
                }

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback to simple truncation
            return {
                "summary": content[:200] + "..." if len(content) > 200 else content,
                "structured_data": {},
            }

    async def _handle_memory_update(
        self,
        new_content: str,
        existing_data: dict,
        path: str,
        namespace: tuple,
        metadata: Optional[dict],
    ) -> dict:
        """Handle updating existing memory content."""
        existing_content = existing_data.get("content", "")

        # Ask LLM how to handle the update
        prompt = [
            f"Memory path: {path}",
            "",
            f"Existing content: {existing_content}",
            "",
            f"New content: {new_content}",
        ]

        if metadata:
            prompt.append(f"New metadata: {json.dumps(metadata)}")

        prompt.extend(
            [
                "",
                "How should we update this memory?",
                "Options:",
                "- replace: Replace old content with new",
                "- append: Add new content to existing",
                "- merge: Intelligently combine both",
                "- skip: Keep existing, ignore new",
                "",
                "Respond in JSON:",
                "{",
                '  "action": "replace" | "append" | "merge" | "skip",',
                '  "reasoning": "explanation",',
                '  "merged_content": "..." (if merge)',
                "}",
            ]
        )

        try:
            response = await self.llm.ainvoke("\n".join(prompt))

            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group())
            else:
                decision = {
                    "action": "append",
                    "reasoning": "Parse error, defaulting to append",
                }

            action = decision.get("action", "append")
            reasoning = decision.get("reasoning", "")

            if action == "replace":
                # Store simplified memory structure for replacement
                from datetime import datetime

                self.memory_store.put(
                    namespace,
                    path,
                    {
                        "raw_text": new_content,
                        "session_date": datetime.now().isoformat(),
                        "confidence": 0.8,
                    },
                )
                return {
                    "action": MemoryAction.REPLACE,
                    "reasoning": reasoning,
                    "new_content": new_content,
                }

            elif action == "append":
                # Combine existing raw text with new content
                existing_raw = existing_data.get("raw_text", "")
                combined_text = f"{existing_raw}\n\n{new_content}"

                from datetime import datetime

                self.memory_store.put(
                    namespace,
                    path,
                    {
                        "raw_text": combined_text,
                        "session_date": datetime.now().isoformat(),
                        "confidence": 0.8,
                    },
                )
                return {
                    "action": MemoryAction.APPEND,
                    "reasoning": reasoning,
                    "new_content": combined_text,
                }

            elif action == "merge":
                # Get existing raw content
                existing_raw = existing_data.get("raw_text", "")
                merged_content = decision.get(
                    "merged_content", f"{existing_raw}\n{new_content}"
                )

                from datetime import datetime

                self.memory_store.put(
                    namespace,
                    path,
                    {
                        "raw_text": merged_content,
                        "session_date": datetime.now().isoformat(),
                        "confidence": 0.8,
                    },
                )
                return {
                    "action": MemoryAction.MERGE,
                    "reasoning": reasoning,
                    "new_content": merged_content,
                }

            else:  # skip
                return {
                    "action": MemoryAction.SKIP,
                    "reasoning": reasoning,
                    "new_content": existing_data.get("raw_text", ""),
                }

        except Exception as e:
            # Fallback to append on error
            existing_raw = existing_data.get("raw_text", "")
            combined = f"{existing_raw}\n\n{new_content}"

            from datetime import datetime

            self.memory_store.put(
                namespace,
                path,
                {
                    "raw_text": combined,
                    "session_date": datetime.now().isoformat(),
                    "confidence": 0.7,
                },
            )
            return {
                "action": MemoryAction.APPEND,
                "reasoning": f"Error in LLM decision, defaulted to append: {e}",
                "new_content": combined,
            }

    def get_stored_memories(self, limit: int = 10) -> list[dict]:
        """Get stored memories from the memory store."""
        if not self.memory_store:
            return []

        namespace = ("memory", self.taxonomy_version.value)
        try:
            results = self.memory_store.search(namespace, filter={}, limit=limit)
            memories = []
            for result in results:
                # Handle tuple format: (namespace, key, value)
                if isinstance(result, tuple) and len(result) == 3:
                    _, key, value = result
                    memories.append(
                        {
                            "path": key,
                            "content": value,
                            "timestamp": (
                                value.get("timestamp")
                                if isinstance(value, dict)
                                else None
                            ),
                        }
                    )
                # Handle object with attributes
                elif hasattr(result, "key") and hasattr(result, "value"):
                    memories.append(
                        {
                            "path": result.key,
                            "content": result.value,
                            "timestamp": getattr(result, "timestamp", None),
                        }
                    )
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    async def get_classification_statistics(self) -> dict:
        """Get statistics about the classification system."""
        return {
            "taxonomy_info": self.taxonomy.get_taxonomy_info(),
            "expansion_stats": self.taxonomy.get_expansion_statistics(),
            "pending_expansions": {
                path: len(items) for path, items in self.pending_expansions.items()
            },
            "confidence_thresholds": self.thresholds,
        }

    def _analyze_hierarchical_consistency(self, new_path: str) -> dict:
        """Analyze hierarchical consistency and suggest improvements."""
        all_paths = self.taxonomy.get_all_paths()
        path_parts = new_path.split(".")

        analysis = {
            "depth": len(path_parts),
            "missing_intermediates": [],
            "similar_paths": [],
            "suggested_improvements": [],
        }

        # Check for missing intermediate levels
        for i in range(1, len(path_parts)):
            intermediate = ".".join(path_parts[: i + 1])
            if intermediate not in all_paths:
                analysis["missing_intermediates"].append(intermediate)

        # Find similar paths in the same domain
        domain = path_parts[0]
        similar = [p for p in all_paths if p.startswith(domain + ".") and p != new_path]
        analysis["similar_paths"] = similar[:5]  # Top 5 similar paths

        # Suggest improvements based on depth and consistency
        if len(path_parts) > 4:
            analysis["suggested_improvements"].append(
                f"Consider reducing depth from {len(path_parts)} to 3-4 levels"
            )

        if len(analysis["missing_intermediates"]) > 1:
            analysis["suggested_improvements"].append(
                f"Add intermediate levels: {', '.join(analysis['missing_intermediates'][:-1])}"
            )

        return analysis

    def _suggest_hierarchical_path(self, content: str, initial_path: str) -> str:
        """Suggest a better hierarchical path based on content and existing taxonomy structure."""
        path_parts = initial_path.split(".")
        content_lower = content.lower()
        content_words = set(content_lower.split())

        # Get all existing paths to learn hierarchy patterns
        all_paths = self.taxonomy.get_all_paths()

        # Analyze existing structure to find better hierarchical patterns
        if len(path_parts) >= 2:
            domain = path_parts[0]

            # Find similar content-based paths in the same domain
            domain_paths = [p for p in all_paths if p.startswith(f"{domain}.")]

            best_match = None
            best_score = 0

            for existing_path in domain_paths:
                existing_parts = existing_path.split(".")
                if len(existing_parts) >= 3:  # Has intermediate levels
                    # Score based on content word overlap
                    path_words = set()
                    for part in existing_parts:
                        path_words.update(part.replace("_", " ").split())

                    overlap = content_words.intersection(path_words)
                    if overlap:
                        score = len(overlap) / len(content_words.union(path_words))
                        if score > best_score and score > 0.2:  # Minimum threshold
                            best_match = existing_path
                            best_score = score

            # If we found a good match, suggest using its intermediate structure
            if best_match:
                match_parts = best_match.split(".")
                if len(match_parts) >= 3 and len(path_parts) == 2:
                    # Use the intermediate structure from the matching path
                    intermediate = match_parts[1]  # Use the area from matching path
                    final_part = path_parts[1]  # Keep our specific category
                    return f"{domain}.{intermediate}.{final_part}"
                elif len(match_parts) >= 3 and len(path_parts) > 3:
                    # Restructure to use the better intermediate from matching path
                    intermediate = match_parts[1]
                    remaining = ".".join(path_parts[2:])
                    return f"{domain}.{intermediate}.{remaining}"

        # No improvement found based on existing structure
        return initial_path

    def get_category_structure(self) -> dict:
        """Get the current category structure for passing to LLM context."""
        all_paths = self.taxonomy.get_all_paths()

        # Analyze current structure
        depth_analysis = {}
        for depth in range(1, 6):
            paths_at_depth = [p for p in all_paths if len(p.split(".")) == depth]
            depth_analysis[f"depth_{depth}"] = len(paths_at_depth)

        return {
            "version": self.taxonomy_version.value,
            "all_paths": all_paths,
            "first_level_categories": [
                p for p in all_paths if "." not in p and p != "other"
            ],
            "structure_snapshot": self.taxonomy.export_for_llm(),
            "depth_analysis": depth_analysis,
            "total_paths": len(all_paths),
        }

    async def evaluate_semantic_appropriateness(
        self, content: str, path: str, context_paths: Optional[list[str]] = None
    ) -> dict:
        """
        Use LLM to evaluate if content semantically belongs in the assigned path.

        Args:
            content: The memory content to evaluate
            path: The taxonomy path where content is stored
            context_paths: Other similar paths for comparison context

        Returns:
            Dict with appropriateness score, reasoning, and suggestions
        """
        # Build evaluation prompt
        prompt_parts = [
            "You are a taxonomy evaluation expert. Analyze whether the given content semantically belongs in the assigned taxonomy path.",
            "",
            f'Content: "{content}"',
            f"Assigned Path: {path}",
            "",
            "Path Components Analysis:",
        ]

        # Break down path components for LLM understanding
        path_parts = path.split(".")
        for i, part in enumerate(path_parts):
            level_name = ["Domain", "Area", "Category", "Subcategory", "Detail"][
                min(i, 4)
            ]
            prompt_parts.append(f"  {level_name}: {part.replace('_', ' ').title()}")

        # Add context of similar paths if available
        if context_paths:
            prompt_parts.extend(
                [
                    "",
                    "Similar paths in taxonomy for comparison:",
                ]
            )
            for similar_path in context_paths[:5]:
                prompt_parts.append(f"  - {similar_path}")

        prompt_parts.extend(
            [
                "",
                "Evaluate:",
                "1. Does the content conceptually belong in this taxonomy path?",
                "2. Is each level of the hierarchy appropriate for this content?",
                "3. Are there better alternative paths in the taxonomy?",
                "4. Is the path depth appropriate for the content's specificity?",
                "",
                "Consider:",
                "- Semantic meaning and conceptual relationships",
                "- Logical hierarchical progression",
                "- Domain appropriateness",
                "- Content specificity vs path granularity",
                "",
                "Respond in JSON format:",
                "{",
                '  "appropriate": true/false,',
                '  "confidence": 0.0-1.0,',
                '  "score": 0-100,',
                '  "reasoning": "detailed explanation of why this classification is good/bad",',
                '  "issues": ["list", "of", "specific", "problems"] or [],',
                '  "suggested_path": "better.path.if.needed" or null,',
                '  "path_quality": "excellent" | "good" | "acceptable" | "poor" | "completely_wrong"',
                "}",
            ]
        )

        try:
            response = await self.llm.ainvoke("\n".join(prompt_parts))

            # Parse LLM response
            if hasattr(response, "content"):
                response_content = response.content
            else:
                response_content = str(response)

            # Extract JSON from response
            import re

            json_match = re.search(r"\{[^{}]*\}", response_content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Fallback if JSON parsing fails
                result = {
                    "appropriate": True,
                    "confidence": 0.5,
                    "score": 50,
                    "reasoning": "Could not parse LLM response",
                    "issues": ["Parse error"],
                    "suggested_path": None,
                    "path_quality": "acceptable",
                }

            # Ensure required fields exist
            result.setdefault("appropriate", result.get("score", 50) >= 70)
            result.setdefault("confidence", 0.5)
            result.setdefault("score", 50)
            result.setdefault("reasoning", "No reasoning provided")
            result.setdefault("issues", [])
            result.setdefault("suggested_path", None)
            result.setdefault("path_quality", "acceptable")

            return result

        except Exception as e:
            logger.error(f"Semantic appropriateness evaluation failed: {e}")
            return {
                "appropriate": True,
                "confidence": 0.0,
                "score": 0,
                "reasoning": f"Evaluation failed: {e}",
                "issues": ["Evaluation error"],
                "suggested_path": None,
                "path_quality": "unknown",
            }

    async def batch_evaluate_semantic_appropriateness(
        self, memory_items: list[dict]
    ) -> list[dict]:
        """
        Evaluate semantic appropriateness for multiple memory items.

        Args:
            memory_items: List of dicts with 'path' and 'content' keys

        Returns:
            List of evaluation results
        """
        results = []

        # Group by domain for context
        domain_groups = {}
        for item in memory_items:
            domain = item["path"].split(".")[0]
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(item)

        # Evaluate each item with domain context
        for item in memory_items:
            domain = item["path"].split(".")[0]
            context_paths = [
                other_item["path"]
                for other_item in domain_groups.get(domain, [])
                if other_item["path"] != item["path"]
            ]

            evaluation = await self.evaluate_semantic_appropriateness(
                item["content"], item["path"], context_paths
            )

            evaluation["item"] = item
            results.append(evaluation)

        return results
