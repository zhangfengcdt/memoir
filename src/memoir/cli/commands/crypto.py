# SPDX-License-Identifier: Apache-2.0
"""
Cryptographic commands for memoir CLI.

Commands: proof, verify, blame
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    EXIT_NOT_FOUND,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("key")
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option("-o", "--output", "output_file", help="Write proof to file")
@pass_context
def proof(ctx: MemoirContext, key: str, namespace: str, output_file: str):
    """Generate a cryptographic proof for a memory.

    Creates a SHA-256 based proof that can be used to verify
    the memory's integrity and existence at this point in time.

    \b
    Examples:
      memoir proof "user.preferences"
      memoir proof "api-key" -n credentials -o proof.txt
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.crypto_service import CryptoService

    service = CryptoService(ctx.store_path)

    try:
        result = service.generate_proof(key, namespace)

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                ctx.success(f"Generated proof for {result.full_key}")
                click.echo(f"  Size: {result.proof_size} bytes")

                if output_file:
                    with open(output_file, "w") as f:
                        f.write(result.proof_b64)
                    click.echo(f"  Written to: {output_file}")
                else:
                    # Show truncated proof
                    proof_preview = (
                        result.proof_b64[:60] + "..."
                        if len(result.proof_b64) > 60
                        else result.proof_b64
                    )
                    click.echo(f"  Proof: {proof_preview}")

                if result.value and ctx.verbose:
                    import json

                    value_str = (
                        json.dumps(result.value)
                        if isinstance(result.value, dict)
                        else str(result.value)
                    )
                    if len(value_str) > 80:
                        value_str = value_str[:80] + "..."
                    click.echo(f"  Value: {value_str}")
            else:
                if result.error and "not found" in result.error.lower():
                    ctx.error(f"Memory not found: {key}", EXIT_NOT_FOUND)
                else:
                    ctx.error(result.error or "Failed to generate proof", EXIT_ERROR)

    except Exception as e:
        ctx.error(f"Failed to generate proof: {e}", EXIT_ERROR)


@click.command()
@click.argument("key")
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option("-p", "--proof", "proof_b64", help="Base64 proof to verify")
@click.option("-f", "--file", "proof_file", help="Read proof from file")
@click.option("--expected", help="Expected value (JSON)")
@pass_context
def verify(
    ctx: MemoirContext,
    key: str,
    namespace: str,
    proof_b64: str,
    proof_file: str,
    expected: str,
):
    """Verify a cryptographic proof.

    Checks if the provided proof is valid for the specified memory key.

    \b
    Examples:
      memoir verify "user.preferences" -p "base64proof..."
      memoir verify "api-key" -n credentials -f proof.txt
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    # Get proof from argument or file
    if proof_file:
        try:
            with open(proof_file) as f:
                proof_b64 = f.read().strip()
        except Exception as e:
            ctx.error(f"Failed to read proof file: {e}", EXIT_ERROR)
    elif not proof_b64:
        ctx.error("Proof required: use --proof or --file", EXIT_ERROR)

    # Parse expected value if provided
    expected_value = None
    if expected:
        import json

        try:
            expected_value = json.loads(expected)
        except json.JSONDecodeError:
            expected_value = expected  # Use as string

    from memoir.services.crypto_service import CryptoService

    service = CryptoService(ctx.store_path)

    try:
        result = service.verify_proof(proof_b64, key, namespace, expected_value)

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                if result.valid:
                    ctx.success(f"Proof is VALID for {result.full_key}")
                    if result.current_value and ctx.verbose:
                        import json

                        value_str = (
                            json.dumps(result.current_value)
                            if isinstance(result.current_value, dict)
                            else str(result.current_value)
                        )
                        click.echo(f"  Current value: {value_str}")
                else:
                    ctx.warn(f"Proof is INVALID for {result.full_key}")
                    click.echo(f"  {result.message}")
            else:
                ctx.error(result.error or "Verification failed", EXIT_ERROR)

    except Exception as e:
        ctx.error(f"Failed to verify proof: {e}", EXIT_ERROR)


@click.command()
@click.argument("key")
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option("-l", "--limit", default=10, help="Maximum entries to show")
@pass_context
def blame(ctx: MemoirContext, key: str, namespace: str, limit: int):
    """Show change history for a memory key.

    Displays git blame-style information showing who changed
    the memory and when.

    \b
    Examples:
      memoir blame "user.preferences"
      memoir blame "api-key" -n credentials -l 5
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.crypto_service import CryptoService

    service = CryptoService(ctx.store_path)

    try:
        entries = service.get_blame(key, namespace)

        if ctx.json_output:
            ctx.output(
                {
                    "key": key,
                    "namespace": namespace,
                    "entries": [e.to_dict() for e in entries[:limit]],
                }
            )
        else:
            if not entries:
                click.echo(f"No history found for {namespace}:{key}")
            else:
                click.echo(f"History for {namespace}:{key}:\n")
                for entry in entries[:limit]:
                    click.echo(
                        click.style(entry.commit, fg="yellow")
                        + f" ({entry.author}, {entry.date[:10] if entry.date else 'unknown'})"
                    )
                    click.echo(f"    {entry.message}")

    except Exception as e:
        ctx.error(f"Failed to get blame info: {e}", EXIT_ERROR)
