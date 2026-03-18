"""Markdown-based taxonomy data source.

Parses YAML frontmatter and structured markdown content into taxonomy data.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


class TaxonomyParseError(Exception):
    """Error parsing taxonomy markdown file."""

    pass


@dataclass
class TaxonomyMetadata:
    """Metadata from taxonomy markdown file frontmatter."""

    type: str  # examples | descriptions | preset
    id: str
    name: str
    domain: str = "general"
    version: str = "1.0.0"
    created: Optional[str] = None
    updated: Optional[str] = None
    author: str = "system"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    taxonomy_version: Optional[str] = None  # For presets (e.g., "simplified")


@dataclass
class TaxonomyData:
    """Parsed taxonomy data from markdown."""

    metadata: TaxonomyMetadata
    examples: Optional[list[tuple[str, str, str]]] = None  # (input, path, reasoning)
    descriptions: Optional[dict[str, str]] = None  # category -> description
    paths: Optional[dict[str, list[str]]] = None  # category -> [subcategory.type, ...]
    raw_content: str = ""


class MarkdownTaxonomySource:
    """
    Markdown file-based taxonomy data source.

    Parses YAML frontmatter and structured markdown content
    into taxonomy data structures.

    Supported types:
    - examples: Classification examples in markdown tables
    - descriptions: Category descriptions in a markdown table
    - preset: Taxonomy paths in bullet lists under headers
    """

    def __init__(self, encoding: str = "utf-8"):
        """Initialize the markdown source parser.

        Args:
            encoding: File encoding to use when reading files.
        """
        self.encoding = encoding

    def load(self, path: Path) -> TaxonomyData:
        """Load and parse a markdown taxonomy file.

        Args:
            path: Path to the markdown file.

        Returns:
            Parsed TaxonomyData.

        Raises:
            TaxonomyParseError: If the file cannot be parsed.
            FileNotFoundError: If the file doesn't exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {path}")

        content = path.read_text(encoding=self.encoding)
        return self.parse(content)

    def parse(self, content: str) -> TaxonomyData:
        """Parse markdown content into TaxonomyData.

        Args:
            content: Raw markdown content.

        Returns:
            Parsed TaxonomyData.

        Raises:
            TaxonomyParseError: If the content cannot be parsed.
        """
        metadata, body = self._split_frontmatter(content)

        if metadata.type == "examples":
            examples = self._parse_examples_tables(body)
            return TaxonomyData(metadata=metadata, examples=examples, raw_content=body)
        elif metadata.type == "descriptions":
            descriptions = self._parse_descriptions_table(body)
            return TaxonomyData(
                metadata=metadata, descriptions=descriptions, raw_content=body
            )
        elif metadata.type == "preset":
            paths = self._parse_preset_lists(body)
            return TaxonomyData(metadata=metadata, paths=paths, raw_content=body)
        else:
            raise TaxonomyParseError(f"Unknown taxonomy type: {metadata.type}")

    def _split_frontmatter(self, content: str) -> tuple[TaxonomyMetadata, str]:
        """Split YAML frontmatter from markdown body.

        Args:
            content: Raw markdown content.

        Returns:
            Tuple of (metadata, body).

        Raises:
            TaxonomyParseError: If frontmatter is missing or invalid.
        """
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content, re.DOTALL)
        if not match:
            raise TaxonomyParseError("Invalid markdown: missing YAML frontmatter")

        yaml_content = match.group(1)
        body = match.group(2)

        try:
            meta_dict = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise TaxonomyParseError(f"Invalid YAML frontmatter: {e}") from e

        # Validate required fields
        required_fields = ["type", "id", "name"]
        for field_name in required_fields:
            if field_name not in meta_dict:
                raise TaxonomyParseError(
                    f"Missing required field in frontmatter: {field_name}"
                )

        # Handle optional list fields that might be None
        if meta_dict.get("tags") is None:
            meta_dict["tags"] = []
        if meta_dict.get("dependencies") is None:
            meta_dict["dependencies"] = []

        metadata = TaxonomyMetadata(**meta_dict)
        return metadata, body

    def _parse_examples_tables(self, body: str) -> list[tuple[str, str, str]]:
        """Parse markdown tables under ## headers into examples.

        Expected format:
        ## category_name
        | Input | Path | Reasoning |
        |-------|------|-----------|
        | My name is Sarah | profile.personal.identity | identity info |

        Args:
            body: Markdown body content.

        Returns:
            List of (input_text, path, reasoning) tuples.
        """
        examples = []

        # Split by ## headers
        sections = re.split(r"^## (\w+)\s*$", body, flags=re.MULTILINE)

        # sections[0] is content before first ##, then alternating category/content
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break

            # category = sections[i]  # Not needed, path includes category
            content = sections[i + 1]

            # Parse table rows
            table_examples = self._parse_table_rows(content)
            examples.extend(table_examples)

        return examples

    def _parse_table_rows(self, content: str) -> list[tuple[str, str, str]]:
        """Parse markdown table rows into example tuples.

        Args:
            content: Content containing a markdown table.

        Returns:
            List of (input, path, reasoning) tuples.
        """
        examples = []
        lines = content.strip().split("\n")

        in_table = False
        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip header row and separator
            if (
                line.startswith("| Input")
                or line.startswith("|--")
                or line.startswith("| ---")
            ):
                in_table = True
                continue

            # Parse data rows
            if in_table and line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.split("|")[1:-1]]
                if len(cells) >= 3:
                    input_text = cells[0]
                    path = cells[1]
                    reasoning = cells[2]
                    if input_text and path:  # Skip empty rows
                        examples.append((input_text, path, reasoning))

        return examples

    def _parse_descriptions_table(self, body: str) -> dict[str, str]:
        """Parse markdown table into category descriptions dict.

        Expected format:
        | Category | Description |
        |----------|-------------|
        | profile | Personal facts... |

        Args:
            body: Markdown body content.

        Returns:
            Dict mapping category to description.
        """
        descriptions = {}
        lines = body.strip().split("\n")

        in_table = False
        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip header row and separator
            if (
                line.startswith("| Category")
                or line.startswith("|--")
                or line.startswith("| ---")
            ):
                in_table = True
                continue

            # Parse data rows
            if in_table and line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.split("|")[1:-1]]
                if len(cells) >= 2:
                    category = cells[0]
                    description = cells[1]
                    if category and description:
                        descriptions[category] = description

        return descriptions

    def _parse_preset_lists(self, body: str) -> dict[str, list[str]]:
        """Parse markdown lists under ## headers into preset paths.

        Expected format:
        ## profile
        - personal.identity
        - personal.demographics

        Args:
            body: Markdown body content.

        Returns:
            Dict mapping category to list of subcategory.type paths.
        """
        paths: dict[str, list[str]] = {}

        # Split by ## headers
        sections = re.split(r"^## (\w+)\s*$", body, flags=re.MULTILINE)

        # sections[0] is content before first ##, then alternating category/content
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break

            category = sections[i].strip()
            content = sections[i + 1]

            # Parse bullet list items
            category_paths = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    path = line[2:].strip()
                    if path:
                        category_paths.append(path)

            if category_paths:
                paths[category] = category_paths

        return paths

    def to_dict(self, data: TaxonomyData) -> dict[str, Any]:
        """Convert TaxonomyData to a dictionary for storage.

        Args:
            data: The taxonomy data to convert.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        result: dict[str, Any] = {
            "metadata": {
                "type": data.metadata.type,
                "id": data.metadata.id,
                "name": data.metadata.name,
                "domain": data.metadata.domain,
                "version": data.metadata.version,
                "author": data.metadata.author,
                "description": data.metadata.description,
                "tags": data.metadata.tags,
                "dependencies": data.metadata.dependencies,
            }
        }

        if data.metadata.created:
            result["metadata"]["created"] = data.metadata.created
        if data.metadata.updated:
            result["metadata"]["updated"] = data.metadata.updated
        if data.metadata.taxonomy_version:
            result["metadata"]["taxonomy_version"] = data.metadata.taxonomy_version

        if data.examples is not None:
            result["examples"] = [
                {"input": inp, "path": path, "reasoning": reason}
                for inp, path, reason in data.examples
            ]

        if data.descriptions is not None:
            result["descriptions"] = data.descriptions

        if data.paths is not None:
            result["paths"] = data.paths

        return result

    def from_dict(self, data: dict[str, Any]) -> TaxonomyData:
        """Convert a dictionary back to TaxonomyData.

        Args:
            data: Dictionary from storage.

        Returns:
            TaxonomyData instance.
        """
        meta_dict = data["metadata"]
        metadata = TaxonomyMetadata(
            type=meta_dict["type"],
            id=meta_dict["id"],
            name=meta_dict["name"],
            domain=meta_dict.get("domain", "general"),
            version=meta_dict.get("version", "1.0.0"),
            created=meta_dict.get("created"),
            updated=meta_dict.get("updated"),
            author=meta_dict.get("author", "system"),
            description=meta_dict.get("description", ""),
            tags=meta_dict.get("tags", []),
            dependencies=meta_dict.get("dependencies", []),
            taxonomy_version=meta_dict.get("taxonomy_version"),
        )

        examples = None
        if "examples" in data:
            examples = [
                (e["input"], e["path"], e["reasoning"]) for e in data["examples"]
            ]

        descriptions = data.get("descriptions")
        paths = data.get("paths")

        return TaxonomyData(
            metadata=metadata,
            examples=examples,
            descriptions=descriptions,
            paths=paths,
        )
