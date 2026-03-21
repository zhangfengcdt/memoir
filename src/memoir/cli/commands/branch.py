"""
Branch commands for memoir CLI.

Commands: branch, checkout, merge, commits
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_GIT_FAILED,
    EXIT_NO_STORE,
    EXIT_NOT_FOUND,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("name", required=False)
@click.option("-d", "--delete", "delete_branch", is_flag=True, help="Delete a branch")
@click.option("-D", "--force-delete", is_flag=True, help="Force delete a branch")
@click.option("--from", "from_ref", help="Create branch from this ref")
@pass_context
def branch(
    ctx: MemoirContext,
    name: str,
    delete_branch: bool,
    force_delete: bool,
    from_ref: str,
):
    """List, create, or delete branches.

    Without arguments, lists all branches.
    With a name, creates a new branch.

    \b
    Examples:
      memoir branch              # List branches
      memoir branch experiment   # Create 'experiment' branch
      memoir branch -d old-test  # Delete 'old-test' branch
      memoir branch feature --from main
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService

    service = BranchService(ctx.store_path)

    try:
        if delete_branch or force_delete:
            if not name:
                ctx.error("Branch name required for deletion", EXIT_ERROR)

            result = service.delete_branch(name, force=force_delete)
            if result.success:
                ctx.success(f"Deleted branch: {name}")
            else:
                ctx.error(
                    result.error or f"Failed to delete branch: {name}", EXIT_GIT_FAILED
                )

        elif name:
            # Create new branch
            result = service.create_branch(name, from_ref=from_ref)
            if result.success:
                ctx.success(f"Created branch: {name}")
            else:
                ctx.error(
                    result.error or f"Failed to create branch: {name}", EXIT_GIT_FAILED
                )

        else:
            # List branches
            info = service.list_branches()

            if ctx.json_output:
                ctx.output(info.to_dict())
            else:
                for b in info.branches:
                    if b == info.current:
                        click.echo(click.style(f"* {b}", fg="green"))
                    else:
                        click.echo(f"  {b}")

    except Exception as e:
        ctx.error(f"Branch operation failed: {e}", EXIT_GIT_FAILED)


@click.command()
@click.argument("target")
@click.option(
    "-b", "--create", "create_branch", is_flag=True, help="Create branch if missing"
)
@pass_context
def checkout(ctx: MemoirContext, target: str, create_branch: bool):
    """Switch to a branch or commit.

    Target can be a branch name or commit hash.

    \b
    Examples:
      memoir checkout main
      memoir checkout -b new-feature
      memoir checkout abc123f
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService

    service = BranchService(ctx.store_path)

    try:
        result = service.checkout(target, create_if_missing=create_branch)

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                ctx.success(result.message or f"Switched to {target}")
            else:
                if "not found" in (result.error or "").lower():
                    ctx.error(f"Branch/commit not found: {target}", EXIT_NOT_FOUND)
                else:
                    ctx.error(
                        result.error or f"Failed to checkout: {target}", EXIT_GIT_FAILED
                    )

    except Exception as e:
        ctx.error(f"Checkout failed: {e}", EXIT_GIT_FAILED)


@click.command()
@click.argument("source")
@click.option("--into", "into_branch", help="Target branch (default: current)")
@click.option(
    "-s",
    "--strategy",
    type=click.Choice(["ours", "theirs", "skip"]),
    default="skip",
    help="Conflict resolution: ours (keep current), theirs (take incoming), skip (ignore conflicts)",
)
@pass_context
def merge(ctx: MemoirContext, source: str, into_branch: str, strategy: str):
    """Merge a branch into current or specified branch.

    Merges SOURCE branch into the current branch, or into
    the branch specified with --into.

    Conflict resolution strategies:
      - ours: Keep current branch's version for conflicts
      - theirs: Take incoming branch's version for conflicts
      - skip: Skip conflicting keys (default, safest)

    \b
    Examples:
      memoir merge feature              # Merge feature into current
      memoir merge experiment --into main
      memoir merge feature -s theirs    # Take incoming changes on conflict
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService, MergeStrategy

    service = BranchService(ctx.store_path)

    try:
        # If target specified, checkout to it first
        if into_branch:
            checkout_result = service.checkout(into_branch)
            if not checkout_result.success:
                ctx.error(
                    f"Failed to checkout target branch: {into_branch}", EXIT_GIT_FAILED
                )

        # Convert strategy string to enum
        merge_strategy = MergeStrategy(strategy)
        result = service.merge(source, strategy=merge_strategy)

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                ctx.success(f"Merged {source} successfully")
                if result.conflicts:
                    click.echo(
                        f"  Resolved {len(result.conflicts)} conflicts using '{strategy}' strategy"
                    )
                    for conflict in result.conflicts[:5]:
                        click.echo(f"    - {conflict}")
                    if len(result.conflicts) > 5:
                        click.echo(f"    ... and {len(result.conflicts) - 5} more")
                if result.commit_hash:
                    click.echo(f"  Merge commit: {result.commit_hash[:8]}")
            else:
                if result.conflicts:
                    ctx.warn(f"Merge has conflicts in {len(result.conflicts)} keys:")
                    for conflict in result.conflicts[:5]:
                        click.echo(f"    - {conflict}")
                    if len(result.conflicts) > 5:
                        click.echo(f"    ... and {len(result.conflicts) - 5} more")
                ctx.error(result.error or "Merge failed", EXIT_GIT_FAILED)

    except Exception as e:
        ctx.error(f"Merge failed: {e}", EXIT_GIT_FAILED)


@click.command()
@click.option("-n", "--limit", default=20, help="Maximum commits to show")
@click.option("--branch", "branch_name", help="Show commits for specific branch")
@click.option("--oneline", is_flag=True, help="Compact single-line format")
@pass_context
def commits(ctx: MemoirContext, limit: int, branch_name: str, oneline: bool):
    """Show commit history.

    Displays recent commits for the current or specified branch.

    \b
    Examples:
      memoir commits
      memoir commits -n 5
      memoir commits --branch main --oneline
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService

    service = BranchService(ctx.store_path)

    try:
        ref = branch_name or "HEAD"
        commits_list = service.get_commits(ref, limit=limit)

        if ctx.json_output:
            ctx.output({"commits": [c.to_dict() for c in commits_list]})
        else:
            if not commits_list:
                click.echo("No commits found.")
            else:
                for commit in commits_list:
                    if oneline:
                        click.echo(
                            click.style(commit.short_hash, fg="yellow")
                            + f" {commit.message}"
                        )
                    else:
                        click.echo(click.style(f"commit {commit.hash}", fg="yellow"))
                        click.echo(f"Author: {commit.author} <{commit.email}>")
                        # Format timestamp
                        from datetime import datetime

                        dt = datetime.fromtimestamp(commit.timestamp)
                        click.echo(f"Date:   {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        click.echo(f"\n    {commit.message}\n")

    except Exception as e:
        ctx.error(f"Failed to get commits: {e}", EXIT_GIT_FAILED)


@click.command("time-travel")
@click.argument("target")
@click.option("-b", "--branch", "branch_name", help="Name for the new branch")
@pass_context
def time_travel(ctx: MemoirContext, target: str, branch_name: str):
    """Travel to a commit and create a branch.

    Creates a new branch at the specified commit, allowing you
    to explore or modify historical memory states.

    \b
    Examples:
      memoir time-travel abc123f
      memoir time-travel abc123f -b my-investigation
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService

    service = BranchService(ctx.store_path)

    try:
        # Create branch name if not provided
        if not branch_name:
            branch_name = f"time-travel-{target[:8]}"

        # Create branch at target commit
        result = service.create_branch(branch_name, from_ref=target)

        if result.success:
            # Checkout the new branch
            checkout_result = service.checkout(branch_name)
            if checkout_result.success:
                if ctx.json_output:
                    ctx.output(
                        {
                            "success": True,
                            "branch": branch_name,
                            "target": target,
                        }
                    )
                else:
                    ctx.success(f"Time traveled to {target[:8]}")
                    click.echo(f"  Created and switched to branch: {branch_name}")
            else:
                ctx.error(
                    f"Created branch but checkout failed: {checkout_result.error}",
                    EXIT_GIT_FAILED,
                )
        else:
            ctx.error(
                result.error or f"Failed to create branch at {target}", EXIT_GIT_FAILED
            )

    except Exception as e:
        ctx.error(f"Time travel failed: {e}", EXIT_GIT_FAILED)


@click.command()
@click.argument("commit1", required=False)
@click.argument("commit2", required=False)
@click.option("--stat", is_flag=True, help="Show statistics only")
@pass_context
def diff(ctx: MemoirContext, commit1: str, commit2: str, stat: bool):
    """Compare memory store between commits.

    Without arguments, shows diff between HEAD and last commit.
    With one argument, shows diff between that commit and HEAD.
    With two arguments, shows diff between the two commits.

    \b
    Examples:
      memoir diff                    # HEAD vs HEAD~1
      memoir diff abc123f            # abc123f vs HEAD
      memoir diff abc123f def456a    # abc123f vs def456a
      memoir diff --stat             # Statistics only
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.branch_service import BranchService

    service = BranchService(ctx.store_path)

    try:
        # Determine commits to diff
        if not commit1:
            c1, c2 = "HEAD~1", "HEAD"
        elif not commit2:
            c1, c2 = commit1, "HEAD"
        else:
            c1, c2 = commit1, commit2

        diff_output = service.get_diff(c1, c2, stat_only=stat)

        if ctx.json_output:
            ctx.output({"diff": diff_output, "from": c1, "to": c2})
        else:
            if not diff_output:
                click.echo("No differences found.")
            else:
                # Colorize diff output
                for line in diff_output.split("\n"):
                    if line.startswith("+") and not line.startswith("+++"):
                        click.echo(click.style(line, fg="green"))
                    elif line.startswith("-") and not line.startswith("---"):
                        click.echo(click.style(line, fg="red"))
                    elif line.startswith("@@"):
                        click.echo(click.style(line, fg="cyan"))
                    else:
                        click.echo(line)

    except Exception as e:
        ctx.error(f"Diff failed: {e}", EXIT_GIT_FAILED)
