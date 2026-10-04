/**
 * Runtime configuration: where the app is running and what it may do.
 *
 * Two hosts serve the same built bundle:
 *
 * - **local** — `memoir ui` serves `dist/` and the `/api/*` endpoints from
 *   one Python process. Configuration arrives as URL parameters
 *   (`?store=<path>&readonly=<0|1>&usellm=<0|1>`), exactly as before.
 * - **cloud** — memoir-cloud serves the bundle on a store's Workspace page
 *   and injects a config object before `</head>`:
 *
 *   ```html
 *   <script>window.__MEMOIR__ = {"apiBase": "/<handle>/<name>/api",
 *     "store": "<handle>/<name>", "ref": "main", "readonly": true,
 *     "profile": "cloud", "backUrl": "/<handle>/<name>"};</script>
 *   ```
 *
 * When the object is absent the app behaves exactly as today. Every field
 * is optional; unknown fields are ignored.
 *
 * `apiBase` replaces the local `/api` prefix: the cloud answers
 * `<apiBase>/store`, `<apiBase>/commits`, … with the same JSON as the local
 * `/api/store`, `/api/commits`, …. Requests stay same-origin so the cloud's
 * session cookie is sent without any header work.
 */

export type Profile = "local" | "cloud";

export interface RuntimeConfig {
  /** Prefix for every API request. Empty means the local `/api`. */
  apiBase: string;
  /** Store to connect to on load (a path locally, an address on the cloud). */
  store: string | null;
  /** Branch to show on load (cloud); `null` means the server's default. */
  ref: string | null;
  /** `true`/`false` when the host decided; `null` means "read the URL". */
  readonly: boolean | null;
  profile: Profile;
  /** Where "Back to store" goes in the cloud profile. */
  backUrl: string | null;
  /** True when `window.__MEMOIR__` was present. */
  injected: boolean;
  /**
   * Optional features the host declares it serves (cloud only), e.g.
   * `["statistics"]`. `null` means "not declared": the cloud then falls
   * back to the built-in list of what it lacks.
   */
  features: string[] | null;
}

interface InjectedConfig {
  apiBase?: unknown;
  store?: unknown;
  ref?: unknown;
  readonly?: unknown;
  profile?: unknown;
  backUrl?: unknown;
  features?: unknown;
}

declare global {
  interface Window {
    __MEMOIR__?: InjectedConfig;
  }
}

const DEFAULTS: RuntimeConfig = {
  apiBase: "",
  store: null,
  ref: null,
  readonly: null,
  profile: "local",
  backUrl: null,
  injected: false,
  features: null,
};

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Parse the injected object (or its absence) into a full config. Exported
 * so tests can feed a fake `window`; the app uses the `runtime` singleton. */
export function readRuntimeConfig(win: Window | undefined = globalWindow()): RuntimeConfig {
  const injected = win?.__MEMOIR__;
  if (!injected || typeof injected !== "object") return DEFAULTS;
  return {
    apiBase: (str(injected.apiBase) ?? "").replace(/\/+$/, ""),
    store: str(injected.store),
    ref: str(injected.ref),
    readonly: typeof injected.readonly === "boolean" ? injected.readonly : null,
    profile: injected.profile === "cloud" ? "cloud" : "local",
    backUrl: str(injected.backUrl),
    injected: true,
    features: Array.isArray(injected.features)
      ? injected.features.filter((f): f is string => typeof f === "string")
      : null,
  };
}

function globalWindow(): Window | undefined {
  return typeof window === "undefined" ? undefined : window;
}

export const runtime: RuntimeConfig = readRuntimeConfig();

/** Base for API requests: `/api` locally, the injected `apiBase` on the cloud. */
export const API_ROOT: string = runtime.apiBase || "/api";

/** Build a request URL for an endpoint name such as `store` or `watch/list`. */
export function apiUrl(endpoint: string, root: string = API_ROOT): string {
  return `${root}/${endpoint.replace(/^\/+/, "")}`;
}

/**
 * Features the cloud profile does not have (and must never request). Each
 * name is checked at the single place that would render or call it.
 *
 * The cloud serves: store, branches, current-branch, branches-status,
 * commits, commit-snapshot, commit-range-diff, branch-merge-preview.
 * Everything else answers 404/405 there.
 */
export type Feature =
  | "statistics" // StatsModal: statistics, onboard, project-onboard, metrics
  | "timeline" // Timeline view
  | "places" // Places view (location)
  | "watch" // Watch view + watch/* endpoints
  | "blame" // memory history in MemoryDetail
  | "llm" // recall, summarize, rewrite
  | "crypto" // proof, verify
  | "branch-match" // branch-match-config read + write
  | "code-repo"; // the local code-repo branch badge

const CLOUD_DISABLED: ReadonlySet<Feature> = new Set<Feature>([
  "statistics",
  "timeline",
  "places",
  "watch",
  "blame",
  "llm",
  "crypto",
  "branch-match",
  "code-repo",
]);

/**
 * Whether ``feature`` is available. Local: always. Cloud: when the host
 * declared a ``features`` list, exactly what it lists; otherwise everything
 * except the built-in ``CLOUD_DISABLED`` set (today's behaviour).
 */
export function featureEnabled(
  feature: Feature,
  profile: Profile = runtime.profile,
  features: readonly string[] | null = runtime.features,
): boolean {
  if (profile === "local") return true;
  if (features) return features.includes(feature);
  return !CLOUD_DISABLED.has(feature);
}

/** In the cloud profile a branch switch is a read (`ref` on the next
 * requests); locally it is `POST checkout`, a write. */
export function branchSwitchIsRead(profile: Profile = runtime.profile): boolean {
  return profile === "cloud";
}
