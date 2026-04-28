# Related Work

This page maps Memoir's design choices to the research that informs them. Sections are organized by which Memoir component the citation grounds, with a short note on relevance — not a literature review, just enough to point a curious reader at the strongest prior art.

## Classifier — Hierarchical Text Classification with LLMs

Memoir's `IntelligentClassifier` performs zero/few-shot hierarchical multi-label classification with a single LLM call against a structured taxonomy prompt. This is a quietly active subfield (2024–2025) with several papers describing nearly the same construction.

- **TELEClass: "Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification with Minimal Supervision", 2024.** Minimally-supervised hierarchical classification that uses LLM-generated class-indicative terms to augment the taxonomy. Closest match to Memoir's `LLMIterativeTaxonomy` expansion logic, where the taxonomy itself grows from observed content. [arXiv:2403.00165](https://arxiv.org/html/2403.00165)
- **TaxMorph: "Hierarchical Text Classification with LLM-Refined Taxonomies".** Frames the LLM as a *taxonomist* — the model can reshape an input hierarchy into a more semantically coherent one. Justifies Memoir's stance that the taxonomy is a living artifact, not a fixed schema. [arXiv:2601.18375](https://arxiv.org/html/2601.18375)
- **Single-pass Hierarchical Text Classification with LLMs (Payberah, 2024).** Single-call hierarchical classification, mirroring Memoir's "one prompt, full taxonomy in context, structured JSON out" approach. Compares flat vs. hierarchical vs. discriminative baselines. [PDF](https://payberah.github.io/files/download/papers/llm_classification.pdf)
- **HierPrompt: "Zero-Shot Hierarchical Text Classification", EMNLP Findings 2025.** Pure zero-shot hierarchical classification — relevant because Memoir's taxonomy can be deployed cold against new domains without labelled data. [PDF](https://aclanthology.org/2025.findings-emnlp.207.pdf)
- **KG-HTC: "Integrating Knowledge Graphs into LLMs for Effective Zero-shot Hierarchical Text Classification", 2025.** Treating the taxonomy as a structured prompt input. Same intuition Memoir uses when injecting `${TAXONOMY_BLOCK}` into the classifier and Stop-hook prompts. [arXiv:2505.05583](https://arxiv.org/html/2505.05583)
- **"Effective Hierarchical Text Classification with Large Language Models", SN Computer Science, 2025.** Survey-style empirical comparison of LLM-based HTC approaches. Useful background. [Springer](https://link.springer.com/article/10.1007/s42979-025-04435-x)

## Long-Term Memory Architecture for LLM Agents

The broader frame Memoir competes in: how should an agent's persistent memory be organized, retrieved, and pruned. Memoir's distinguishing claim — *versionable, branchable, taxonomy-keyed memory with cryptographic proofs* — sits adjacent to but not duplicated by these systems.

- **Packer et al., "MemGPT: Towards LLMs as Operating Systems", 2023.** The foundational hierarchical-memory-tier paper (main / recall / archival). Memoir's branches and namespaces are an *alternative topology* for the same problem — same goal of fitting unbounded history into a bounded working set, different solution. [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
- **Xu et al., "A-MEM: Agentic Memory for LLM Agents", 2025.** Current SOTA on multi-hop memory benchmarks, reporting 85–93% token-usage reduction vs. MemGPT. A-MEM's self-organized note-linking is the closest published analog to Memoir's `related_keys` cross-references. [arXiv:2502.12110](https://arxiv.org/pdf/2502.12110)
- **Mem0: "Building Production-Ready AI Agents with Scalable Long-Term Memory", 2025.** The production-systems framing Memoir competes with most directly. Useful as a comparison point on operational concerns (latency, cost, retrieval quality). [arXiv:2504.19413](https://arxiv.org/pdf/2504.19413)
- **"Hierarchical Memory for High-Efficiency Long-Term Reasoning in LLM Agents", July 2025.** Direct support for the hierarchical-taxonomy-as-memory thesis Memoir advances.
- **"Memory in the Age of AI Agents: A Survey", 2025.** The survey to cite when framing Memoir's place in the landscape; identifies five mechanism families (context-resident compression, retrieval-augmented stores, reflective self-improvement, hierarchical virtual context, policy-learned management). Memoir is primarily *retrieval-augmented + hierarchical virtual context* with a versioning twist. [Paper list](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- **"Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers", 2026.** Recent companion survey covering evaluation methodology — useful for grounding Memoir's benchmark choices. [arXiv:2603.07670](https://arxiv.org/html/2603.07670v1)

## Versioned Structured Data and Content-Addressed Storage

Memoir's git-like-versioning-for-memory thesis sits on a body of systems work, much of it grey literature, but with one foundational academic citation.

- **Benet, "IPFS — Content Addressed, Versioned, P2P File System", 2014.** The canonical content-addressed-DAG paper. Memoir applies the same construction (immutable content-addressed chunks → Merkle DAG of revisions) to memory blobs rather than files. [arXiv:1407.3561](https://arxiv.org/pdf/1407.3561)

## Memento Pattern — Episodic, Semantic, and Spatial Memory

Memoir's three Memento containers (`ProfileMemento`, `TimelineMemento`, the location-keyed equivalent) map cleanly onto the cognitive-science distinction between *semantic*, *episodic*, and *spatial* memory that has been formalized for LLM agents over the last two years. This is the most direct theoretical alignment in Memoir.

- **Park et al., "Generative Agents: Interactive Simulacra of Human Behavior", UIST 2023.** Introduces the episodic-event-stream + reflection-into-semantic-memory pattern that Memoir's Timeline → Profile flow mirrors. Their three retrieval scores (recency, importance, relevance) define the design space Memoir's search engine operates in. [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)
- **Sumers et al., "Cognitive Architectures for Language Agents" (CoALA), 2023.** The canonical academic taxonomy for agent memory; episodic / semantic / procedural categories are CoALA's. Letta, Mem0, and LangChain all use CoALA as their framing — Memoir's Mementos sit in the same ontology. [arXiv:2309.02427](https://arxiv.org/pdf/2309.02427)
- **"Synapse: Empowering LLM Agents with Episodic-Semantic Memory via Spreading Activation", 2025.** Activation-based retrieval across the episodic ↔ semantic boundary. Closest prior art for Memoir's `related_keys` cross-reference design, which is structurally a static spreading-activation graph. [arXiv:2601.02744](https://arxiv.org/html/2601.02744v2)

## Notable Gaps

Two parts of Memoir's design currently sit ahead of the published literature, worth flagging honestly:

- **"Memory worthiness" filtering** — the should-this-turn-become-a-memory? decision Memoir's Stop hook performs. Generative Agents and A-MEM both touch importance scoring, but no paper is dedicated to this filter.
- **Multi-key sibling backlinks at storage time** — A-MEM's note-linking is the closest analog, but it is computed at retrieval time, not frozen into the blob at write. Memoir's design (write-time `related_keys`, edit-preserved) appears to be novel.

These are reasonable areas for a future Memoir whitepaper to claim contribution.
