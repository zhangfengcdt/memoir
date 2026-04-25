import { create } from "zustand";

/**
 * Server-set feature flags read from the URL on first load.
 *
 * The CLI launches ``memoir ui --v2 [--no-readonly] [--usellm]`` and
 * encodes the resulting flags into the URL it opens:
 *   ``http://…/?store=<path>&readonly=<0|1>&usellm=<0|1>``
 *
 * Once parsed, these flags don't change for the lifetime of the
 * session — they reflect how the *server* was started, not user
 * preference. UI elements that depend on them (LLM-driven editors,
 * mutating actions) read this slice to decide whether to render.
 */
export interface ConfigSlice {
  /** ``true`` when the server allows mutating writes (``--no-readonly``). */
  writable: boolean;
  /** ``true`` when LLM features (recall, summarize, rewrite) are enabled. */
  useLLM: boolean;
}

function parseFlag(value: string | null, defaultValue: boolean): boolean {
  if (value === null) return defaultValue;
  return value === "1" || value.toLowerCase() === "true";
}

function initial(): ConfigSlice {
  if (typeof window === "undefined") {
    return { writable: false, useLLM: false };
  }
  const params = new URL(window.location.href).searchParams;
  // The query string uses ``readonly=1`` for readonly mode; we flip
  // semantics to ``writable`` because every consumer asks "can I write?".
  const readonly = parseFlag(params.get("readonly"), true);
  const useLLM = parseFlag(params.get("usellm"), false);
  return { writable: !readonly, useLLM };
}

export const useConfig = create<ConfigSlice>(() => initial());
