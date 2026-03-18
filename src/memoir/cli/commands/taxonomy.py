"""
Taxonomy commands for memoir CLI.

Commands: init, load, list, show
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.group()
def taxonomy():
    """Manage taxonomy data in the memory store.

    Taxonomy provides classification examples, category descriptions,
    and path presets that help the classifier organize memories.

    \b
    COMMANDS:
      init   Initialize store with builtin taxonomy
      load   Load an external taxonomy markdown file
      list   List loaded taxonomies
      show   Show details of a specific taxonomy

    \b
    Examples:
      memoir taxonomy init
      memoir taxonomy load /path/to/custom.md
      memoir taxonomy list
    """
    pass


@taxonomy.command("init")
@click.option(
    "--force",
    is_flag=True,
    help="Replace existing taxonomy data",
)
@pass_context
def init_taxonomy(ctx: MemoirContext, force: bool):
    """Initialize store with builtin taxonomy.

    Loads the builtin taxonomy files containing ~215 classification examples,
    16 category descriptions, and ~157 preset paths.

    \b
    Examples:
      memoir taxonomy init
      memoir taxonomy init --force

    \b
    JSON output includes: loaded (by type), saved (count)
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader

    try:
        store = ProllyTreeStore(ctx.store_path)
        loader = TaxonomyLoader(store)

        # Check if taxonomy already exists
        if not force and loader.has_taxonomy_in_store():
            ctx.error(
                "Taxonomy already initialized. Use --force to replace.",
                EXIT_ERROR,
            )

        merge_strategy = "replace" if force else "extend"
        result = loader.init_store(
            include_builtin=True,
            merge_strategy=merge_strategy,
        )

        if ctx.json_output:
            ctx.output({"success": True, **result})
        else:
            loaded = result.get("loaded", {})
            ctx.success(
                f"Initialized taxonomy: "
                f"{loaded.get('examples', 0)} examples, "
                f"{loaded.get('descriptions', 0)} descriptions, "
                f"{loaded.get('preset', 0)} presets"
            )
    except Exception as e:
        ctx.error(f"Failed to initialize taxonomy: {e}", EXIT_ERROR)


@taxonomy.command("load")
@click.argument("path", type=click.Path(exists=True))
@pass_context
def load_taxonomy(ctx: MemoirContext, path: str):
    """Load an external taxonomy markdown file.

    The file must be a valid taxonomy markdown with YAML frontmatter
    specifying type (examples, descriptions, preset), id, name, and version.

    \b
    Examples:
      memoir taxonomy load /path/to/custom-examples.md
      memoir taxonomy load ~/taxonomy/my-preset.md

    \b
    JSON output includes: id, type, name, domain
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader

    try:
        store = ProllyTreeStore(ctx.store_path)
        loader = TaxonomyLoader(store)

        # Load and save
        taxonomy_id = loader.load_external(path)
        loader.save_to_store(taxonomy_id)

        # Get metadata for output
        data = loader.registry.get(taxonomy_id)

        if ctx.json_output:
            ctx.output(
                {
                    "success": True,
                    "id": taxonomy_id,
                    "type": data.metadata.type,
                    "name": data.metadata.name,
                    "domain": data.metadata.domain,
                }
            )
        else:
            ctx.success(
                f"Loaded '{data.metadata.name}' ({data.metadata.type}) as {taxonomy_id}"
            )
    except Exception as e:
        ctx.error(f"Failed to load taxonomy: {e}", EXIT_ERROR)


@taxonomy.command("list")
@pass_context
def list_taxonomies(ctx: MemoirContext):
    """List all taxonomies in the store.

    Shows taxonomies grouped by type (examples, descriptions, preset).

    \b
    Examples:
      memoir taxonomy list
      memoir taxonomy list --json

    \b
    JSON output includes: taxonomies (by type), total
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader

    try:
        store = ProllyTreeStore(ctx.store_path)
        loader = TaxonomyLoader(store)

        taxonomies = loader.list_stored_taxonomies()
        total = sum(len(ids) for ids in taxonomies.values())

        if ctx.json_output:
            ctx.output({"taxonomies": taxonomies, "total": total})
        else:
            if not taxonomies:
                click.echo("No taxonomies loaded. Use 'memoir taxonomy init' to load.")
                return

            click.echo(f"Taxonomies ({total} total):\n")
            for tax_type, ids in taxonomies.items():
                click.echo(f"  {tax_type.upper()}:")
                for tid in ids:
                    meta = loader.get_taxonomy_metadata(tid)
                    if meta:
                        click.echo(f"    - {tid}: {meta.get('name', 'Unknown')}")
                    else:
                        click.echo(f"    - {tid}")
                click.echo()
    except Exception as e:
        ctx.error(f"Failed to list taxonomies: {e}", EXIT_ERROR)


@taxonomy.command("show")
@click.argument("taxonomy_id")
@pass_context
def show_taxonomy(ctx: MemoirContext, taxonomy_id: str):
    """Show details of a specific taxonomy.

    \b
    Examples:
      memoir taxonomy show general-examples
      memoir taxonomy show simplified-preset --json

    \b
    JSON output includes: metadata, stats (type-specific counts)
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader

    try:
        store = ProllyTreeStore(ctx.store_path)
        loader = TaxonomyLoader(store)

        meta = loader.get_taxonomy_metadata(taxonomy_id)
        if not meta:
            ctx.error(f"Taxonomy not found: {taxonomy_id}", EXIT_ERROR)

        # Get type-specific stats
        stats = {}
        tax_type = meta.get("type")

        if tax_type == "examples":
            examples = loader.get_examples_from_store()
            stats["example_count"] = len(examples)
        elif tax_type == "descriptions":
            descriptions = loader.get_descriptions_from_store()
            stats["category_count"] = len(descriptions)
        elif tax_type == "preset":
            paths = loader.get_preset_paths_from_store(taxonomy_id)
            stats["category_count"] = len(paths)
            stats["path_count"] = sum(len(p) for p in paths.values())

        if ctx.json_output:
            ctx.output({"metadata": meta, "stats": stats})
        else:
            click.echo(f"Taxonomy: {taxonomy_id}\n")
            click.echo(f"  Name: {meta.get('name', 'Unknown')}")
            click.echo(f"  Type: {meta.get('type', 'Unknown')}")
            click.echo(f"  Domain: {meta.get('domain', 'Unknown')}")
            click.echo(f"  Version: {meta.get('version', 'Unknown')}")
            if meta.get("description"):
                click.echo(f"  Description: {meta.get('description')}")
            click.echo()
            if stats:
                click.echo("  Stats:")
                for key, value in stats.items():
                    click.echo(f"    {key}: {value}")
    except Exception as e:
        ctx.error(f"Failed to show taxonomy: {e}", EXIT_ERROR)
