import { listCommands, type CommandDef } from "./registry";

/**
 * Match an input string against the command registry for autocomplete.
 *
 * Rules:
 * - Empty / non-slash input → no matches (the dropdown stays hidden).
 * - Bare ``/`` → all commands, in registry order.
 * - ``/<prefix>`` → commands whose canonical name OR any alias starts
 *   with ``<prefix>``. Canonical-name matches rank first; alias-only
 *   matches come after. Within each group, commands are sorted by name.
 * - ``/<word> <args>`` → drops the dropdown (the user is past command
 *   selection and is filling args).
 */
export function matchCommands(input: string): CommandDef[] {
  if (!input.startsWith("/")) return [];
  const tail = input.slice(1);
  // Once a space appears, the user is typing arguments, not picking a
  // command. The autocomplete should get out of the way.
  if (tail.includes(" ")) return [];

  const all = listCommands();
  if (tail.length === 0) return all;

  const lower = tail.toLowerCase();
  const canonical: CommandDef[] = [];
  const aliasOnly: CommandDef[] = [];

  for (const def of all) {
    if (def.name.toLowerCase().startsWith(lower)) {
      canonical.push(def);
    } else if (def.aliases.some((a) => a.toLowerCase().startsWith(lower))) {
      aliasOnly.push(def);
    }
  }

  return [...canonical, ...aliasOnly];
}
