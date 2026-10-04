import { create } from "zustand";
import { runtime, type Profile } from "../config/runtime";

/**
 * Host-set feature flags, fixed for the lifetime of the session.
 *
 * Locally the CLI launches ``memoir ui [--no-readonly] [--usellm]`` and
 * encodes the flags into the URL it opens:
 *   ``http://…/?store=<path>&readonly=<0|1>&usellm=<0|1>``
 * On the cloud the Workspace page injects ``window.__MEMOIR__`` instead
 * (see ``config/runtime.ts``); its ``readonly`` wins over the URL.
 *
 * UI elements that depend on these read this slice to decide whether to
 * render. ``writable`` is the one gate for every write control: when it is
 * false no button, chip or command that would POST a change renders, in
 * any profile. (The local server enforces nothing itself; that is
 * unchanged.)
 */
export interface ConfigSlice {
  /** ``true`` when the host allows mutating writes. */
  writable: boolean;
  /** ``true`` when LLM features (recall, summarize, rewrite) are enabled. */
  useLLM: boolean;
  /** ``"local"`` (``memoir ui``) or ``"cloud"`` (memoir-cloud Workspace). */
  profile: Profile;
  /** Cloud profile: where the "Back to store" link goes. */
  backUrl: string | null;
  /** Optional features the host declared (``window.__MEMOIR__.features``). */
  features: string[] | null;
}

function parseFlag(value: string | null, defaultValue: boolean): boolean {
  if (value === null) return defaultValue;
  return value === "1" || value.toLowerCase() === "true";
}

export function initialConfig(
  rt = runtime,
  href: string | null = typeof window === "undefined" ? null : window.location.href,
): ConfigSlice {
  const params = href ? new URL(href).searchParams : new URLSearchParams();
  // The query string uses ``readonly=1`` for readonly mode; we flip
  // semantics to ``writable`` because every consumer asks "can I write?".
  // Default to ``writable`` (readonly=false) when nothing says otherwise,
  // matching the CLI's --readonly/--no-readonly default.
  const readonly = rt.readonly ?? parseFlag(params.get("readonly"), false);
  // The cloud has no LLM endpoints, whatever the URL says.
  const useLLM = rt.profile === "cloud" ? false : parseFlag(params.get("usellm"), false);
  return {
    writable: !readonly,
    useLLM,
    profile: rt.profile,
    backUrl: rt.backUrl,
    features: rt.features,
  };
}

export const useConfig = create<ConfigSlice>(() => initialConfig());
