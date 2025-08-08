"""
Data source interfaces and implementations for taxonomy loading.
Provides flexible, extensible ways to load taxonomy data from various sources.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


class TaxonomyDataSource(ABC):
    """
    Abstract base class for taxonomy data sources.

    Supports loading taxonomy data from various sources like JSON files,
    databases, APIs, or any custom implementation.
    """

    @abstractmethod
    def load_taxonomy_data(self) -> dict[str, Any]:
        """
        Load taxonomy data from the data source.

        Returns:
            Dictionary containing the complete taxonomy structure

        Raises:
            TaxonomyLoadError: If data cannot be loaded
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the data source is available/accessible.

        Returns:
            True if data source can be accessed, False otherwise
        """
        pass

    def get_metadata(self) -> dict[str, Any]:
        """
        Get metadata about the taxonomy data source.

        Returns:
            Dictionary with metadata like version, last_modified, source_type, etc.
        """
        return {
            "source_type": self.__class__.__name__,
            "description": "Taxonomy data source",
        }


class FileBasedTaxonomyDataSource(TaxonomyDataSource):
    """
    Base class for file-based taxonomy data sources.
    Provides common file handling functionality.
    """

    def __init__(self, file_path: Union[str, Path]):
        """
        Initialize file-based data source.

        Args:
            file_path: Path to the taxonomy data file
        """
        self.file_path = Path(file_path)

    def is_available(self) -> bool:
        """Check if the file exists and is readable."""
        return self.file_path.exists() and self.file_path.is_file()

    def get_metadata(self) -> dict[str, Any]:
        """Get file-based metadata."""
        metadata = super().get_metadata()
        metadata.update(
            {
                "file_path": str(self.file_path),
                "file_exists": self.file_path.exists(),
            }
        )

        if self.file_path.exists():
            stat = self.file_path.stat()
            metadata.update(
                {
                    "file_size": stat.st_size,
                    "last_modified": stat.st_mtime,
                }
            )

        return metadata


class JSONTaxonomyDataSource(FileBasedTaxonomyDataSource):
    """
    JSON file-based taxonomy data source.

    Loads taxonomy data from a JSON file with optional schema validation.
    """

    def __init__(self, file_path: Union[str, Path], encoding: str = "utf-8"):
        """
        Initialize JSON data source.

        Args:
            file_path: Path to JSON file containing taxonomy data
            encoding: File encoding (default: utf-8)
        """
        super().__init__(file_path)
        self.encoding = encoding

    def load_taxonomy_data(self) -> dict[str, Any]:
        """
        Load taxonomy data from JSON file.

        Returns:
            Dictionary containing taxonomy structure

        Raises:
            TaxonomyLoadError: If file cannot be read or JSON is invalid
        """
        try:
            if not self.is_available():
                raise TaxonomyLoadError(f"JSON file not available: {self.file_path}")

            with open(self.file_path, encoding=self.encoding) as f:
                data = json.load(f)

            # Basic validation
            if not isinstance(data, dict):
                raise TaxonomyLoadError("Taxonomy data must be a dictionary")

            logger.info(f"Successfully loaded taxonomy from {self.file_path}")
            return data

        except json.JSONDecodeError as e:
            raise TaxonomyLoadError(f"Invalid JSON in {self.file_path}: {e}")
        except Exception as e:
            raise TaxonomyLoadError(
                f"Failed to load taxonomy from {self.file_path}: {e}"
            )


class HardcodedTaxonomyDataSource(TaxonomyDataSource):
    """
    Fallback data source with hardcoded taxonomy data.

    Used as a last resort when no other data sources are available.
    Contains a minimal but functional taxonomy structure.
    """

    def is_available(self) -> bool:
        """Hardcoded data is always available."""
        return True

    def load_taxonomy_data(self) -> dict[str, Any]:
        """
        Return hardcoded minimal taxonomy structure.

        This is a simplified version for fallback use.
        """
        return {
            "profile": {
                "personal": {
                    "identity": {
                        "name": ["first", "middle", "last", "nickname"],
                        "age": ["current", "birthday"],
                        "location": ["current", "hometown"],
                    }
                },
                "professional": {
                    "current": {
                        "company": ["name", "industry"],
                        "position": ["title", "level"],
                        "skills": ["technical", "soft"],
                    }
                },
            },
            "preferences": {
                "personal": {
                    "lifestyle": ["daily", "hobbies", "interests"],
                    "values": ["core", "priorities"],
                },
                "technology": {
                    "tools": ["software", "hardware"],
                    "platforms": ["social", "work"],
                },
            },
            "experience": {
                "work": {
                    "projects": ["completed", "current"],
                    "achievements": ["awards", "recognition"],
                },
                "education": {
                    "formal": ["degrees", "certifications"],
                    "informal": ["courses", "self_study"],
                },
            },
            "context": {
                "current": {
                    "session": ["topic", "mood"],
                    "location": ["physical", "virtual"],
                }
            },
            "knowledge": {
                "domains": {
                    "technical": ["programming", "systems"],
                    "business": ["strategy", "operations"],
                }
            },
            "relationships": {
                "personal": {
                    "family": ["immediate", "extended"],
                    "friends": ["close", "casual"],
                },
                "professional": {
                    "colleagues": ["current", "former"],
                    "mentors": ["current", "former"],
                },
            },
            "goals": {
                "short_term": {
                    "personal": ["health", "skills"],
                    "professional": ["projects", "advancement"],
                },
                "long_term": {
                    "career": ["direction", "milestones"],
                    "life": ["major", "aspirational"],
                },
            },
            "behavior": {
                "patterns": {
                    "work": ["productivity", "communication"],
                    "personal": ["habits", "routines"],
                }
            },
        }

    def get_metadata(self) -> dict[str, Any]:
        """Get hardcoded data source metadata."""
        metadata = super().get_metadata()
        metadata.update(
            {
                "description": "Fallback hardcoded taxonomy data",
                "version": "1.0.0",
                "categories": 8,
            }
        )
        return metadata


class DatabaseTaxonomyDataSource(TaxonomyDataSource):
    """
    Database-based taxonomy data source.

    Template for future database integration. Loads taxonomy from SQL/NoSQL databases.
    """

    def __init__(self, connection_string: str, table_name: str = "taxonomy"):
        """
        Initialize database data source.

        Args:
            connection_string: Database connection string
            table_name: Table/collection name containing taxonomy data
        """
        self.connection_string = connection_string
        self.table_name = table_name
        self._connection = None

    def is_available(self) -> bool:
        """Check if database connection can be established."""
        try:
            # This would implement actual database connection testing
            # For now, return False as this is a template
            return False
        except Exception:
            return False

    def load_taxonomy_data(self) -> dict[str, Any]:
        """
        Load taxonomy data from database.

        This is a template implementation. In practice, this would:
        1. Connect to the database
        2. Query taxonomy structure/data
        3. Transform to expected format
        4. Return structured data
        """
        raise TaxonomyLoadError("Database data source not yet implemented")

    def get_metadata(self) -> dict[str, Any]:
        """Get database source metadata."""
        metadata = super().get_metadata()
        metadata.update(
            {
                "connection_string": self.connection_string[:50]
                + "...",  # Truncate for security
                "table_name": self.table_name,
                "status": "template_implementation",
            }
        )
        return metadata


class TaxonomyLoadError(Exception):
    """Exception raised when taxonomy data cannot be loaded from a source."""

    pass


class TaxonomyDataSourceManager:
    """
    Manages multiple taxonomy data sources with fallback chain.

    Tries data sources in order until one succeeds, with intelligent fallback.
    """

    def __init__(self, data_sources: Optional[list[TaxonomyDataSource]] = None):
        """
        Initialize data source manager.

        Args:
            data_sources: List of data sources to try in order.
                         If None, uses default sources.
        """
        self.data_sources = data_sources or self._get_default_sources()
        self._cached_data = None
        self._successful_source = None

    def _get_default_sources(self) -> list[TaxonomyDataSource]:
        """Get default data source chain."""
        # Try to find JSON file in standard locations
        possible_json_locations = [
            Path(__file__).parent / "data" / "semantic_taxonomy.json",
            Path(__file__).parent / "semantic_taxonomy.json",
            Path("taxonomy_data.json"),
            Path("data/taxonomy_data.json"),
        ]

        sources = []

        # Add JSON sources for any files that exist
        for json_path in possible_json_locations:
            json_source = JSONTaxonomyDataSource(json_path)
            sources.append(json_source)

        # Always add hardcoded fallback as last resort
        sources.append(HardcodedTaxonomyDataSource())

        return sources

    def load_taxonomy_data(self, use_cache: bool = True) -> dict[str, Any]:
        """
        Load taxonomy data from first available source.

        Args:
            use_cache: Whether to use cached data if available

        Returns:
            Taxonomy data dictionary

        Raises:
            TaxonomyLoadError: If no data sources are available
        """
        if use_cache and self._cached_data is not None:
            logger.debug(f"Using cached taxonomy data from {self._successful_source}")
            return self._cached_data

        for source in self.data_sources:
            try:
                if source.is_available():
                    logger.info(
                        f"Attempting to load taxonomy from {type(source).__name__}"
                    )
                    data = source.load_taxonomy_data()

                    # Cache successful load
                    self._cached_data = data
                    self._successful_source = type(source).__name__

                    logger.info(
                        f"Successfully loaded taxonomy from {self._successful_source}"
                    )
                    return data
                else:
                    logger.debug(f"{type(source).__name__} not available, skipping")

            except TaxonomyLoadError as e:
                logger.warning(f"Failed to load from {type(source).__name__}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error with {type(source).__name__}: {e}")
                continue

        raise TaxonomyLoadError("No available taxonomy data sources")

    def get_source_status(self) -> dict[str, Any]:
        """
        Get status of all configured data sources.

        Returns:
            Dictionary with status information for each source
        """
        status = {
            "sources": [],
            "successful_source": self._successful_source,
            "cached_data_available": self._cached_data is not None,
        }

        for i, source in enumerate(self.data_sources):
            source_info = {
                "index": i,
                "type": type(source).__name__,
                "available": source.is_available(),
                "metadata": source.get_metadata(),
            }
            status["sources"].append(source_info)

        return status

    def add_data_source(self, source: TaxonomyDataSource, priority: int = -1):
        """
        Add a new data source to the chain.

        Args:
            source: Data source to add
            priority: Position in chain (0=highest, -1=append to end)
        """
        if priority == -1:
            self.data_sources.append(source)
        else:
            self.data_sources.insert(priority, source)

        # Clear cache when sources change
        self._cached_data = None
        self._successful_source = None

    def clear_cache(self):
        """Clear cached taxonomy data."""
        self._cached_data = None
        self._successful_source = None
