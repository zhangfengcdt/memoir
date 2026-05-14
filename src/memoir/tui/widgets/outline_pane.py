# SPDX-License-Identifier: Apache-2.0
"""OutlinePane — filter bar + Tree of memories | MemoryViewer.

Mirrors the web UI's ``FilterBar`` (Match / Exclude / Depth) for the
``default`` namespace. Plain text patterns match as a substring; the
presence of ``*`` or ``?`` switches to ``fnmatch.fnmatchcase`` glob.
Depth ``All``/``L1``/``L2``/``L3`` caps the rendered tree at N
segments — matches the ``maxDepth`` prune in ``buildTaxonomy.ts``.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Select, Static, Tree
from textual.worker import Worker, WorkerState

from memoir.tui.widgets.memory_viewer import MemoryViewer

if TYPE_CHECKING:
    from typing import ClassVar

    from textual.app import ComposeResult

    from memoir.tui.data import DataLoader, MemoryEntry


@dataclass
class _Leaf:
    """Payload attached to a leaf tree node so selection can read it back.

    Body is fetched lazily when the user selects the leaf — keeps initial
    tree construction cheap.
    """

    namespace: str
    path: str


# Sentinel used as a Select option for "no depth cap".
_DEPTH_ALL = 0


class OutlinePane(Vertical):
    DEFAULT_CSS = """
    OutlinePane #outline-filter-bar {
        height: 3;
        padding: 0 1;
    }
    OutlinePane #outline-filter-bar > * {
        margin-right: 1;
    }
    OutlinePane .filter-label {
        width: auto;
        padding: 1 0;
        color: $text-muted;
    }
    OutlinePane #outline-match,
    OutlinePane #outline-exclude {
        width: 1fr;
    }
    OutlinePane #outline-depth {
        width: 14;
    }
    OutlinePane > Horizontal#outline-body {
        height: 1fr;
    }
    OutlinePane Tree {
        width: 40%;
    }
    OutlinePane MemoryViewer {
        width: 60%;
        border-left: solid $accent;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("slash", "focus_match", "Match", show=True),
        Binding("e", "focus_exclude", "Exclude", show=True),
    ]

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader
        self._memories: list[MemoryEntry] = []
        self._loaded = False
        self._load_worker: Worker | None = None
        self._body_worker: Worker | None = None
        # Filter state (lowercased — patterns are case-insensitive).
        self._match_text = ""
        self._exclude_text = ""
        self._max_depth: int = _DEPTH_ALL  # 0 = no cap

    def compose(self) -> ComposeResult:
        with Horizontal(id="outline-filter-bar"):
            yield Static("Match:", classes="filter-label")
            yield Input(placeholder="text or *.glob", id="outline-match")
            yield Static("Exclude:", classes="filter-label")
            yield Input(placeholder="text or *.glob", id="outline-exclude")
            yield Static("Depth:", classes="filter-label")
            yield Select(
                options=[("All", _DEPTH_ALL), ("L1", 1), ("L2", 2), ("L3", 3)],
                value=_DEPTH_ALL,
                allow_blank=False,
                id="outline-depth",
            )
        with Horizontal(id="outline-body"):
            tree: Tree[_Leaf] = Tree("Memories", id="outline-tree")
            tree.show_root = False
            yield tree
            yield MemoryViewer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def ensure_loaded(self) -> None:
        if self._loaded or (
            self._load_worker is not None
            and self._load_worker.state
            not in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)
        ):
            return
        viewer = self.query_one(MemoryViewer)
        viewer.show("Loading outline…", dim=True)
        self._load_worker = self.run_worker(
            self._fetch_memories,
            exclusive=True,
            thread=True,
            description="outline:load",
        )

    def refresh_data(self) -> None:
        self._loaded = False
        self.ensure_loaded()

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _fetch_memories(self) -> None:
        memories = self._loader.get_memories()
        self.app.call_from_thread(self._render_memories, memories)

    def _render_memories(self, memories: list[MemoryEntry]) -> None:
        self._memories = memories
        self._loaded = True
        self._rebuild_tree()
        viewer = self.query_one(MemoryViewer)
        if memories:
            viewer.show(
                f"Select a memory on the left. {len(memories)} entries.",
                dim=True,
            )
        else:
            viewer.show("No memories in this store yet.", dim=True)

    # ------------------------------------------------------------------
    # Filter inputs
    # ------------------------------------------------------------------

    def action_focus_match(self) -> None:
        self.query_one("#outline-match", Input).focus()

    def action_focus_exclude(self) -> None:
        self.query_one("#outline-exclude", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "outline-match":
            self._match_text = event.value.strip().lower()
        elif event.input.id == "outline-exclude":
            self._exclude_text = event.value.strip().lower()
        else:
            return
        self._rebuild_tree()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("outline-match", "outline-exclude"):
            self.query_one(Tree).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "outline-depth":
            return
        value = event.value
        try:
            self._max_depth = int(value) if value is not None else _DEPTH_ALL
        except (TypeError, ValueError):
            self._max_depth = _DEPTH_ALL
        self._rebuild_tree()

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def _rebuild_tree(self) -> None:
        tree = self.query_one(Tree)
        tree.clear()
        filtered = self._filtered_memories()
        if not filtered:
            return

        # Single rooted tree over dotted-path segments — no L1 namespace
        # group since we filter to default-only above.
        root: dict = {}
        for entry in filtered:
            node = root
            segments = entry.path.split(".") if entry.path else []
            for seg in segments[:-1]:
                child = node.setdefault(seg, {})
                if isinstance(child, _Leaf):
                    # A leaf and a subtree share the same path prefix.
                    # Promote the leaf into a subtree under an empty key
                    # so both still appear.
                    node[seg] = {"": child}
                    child = node[seg]
                node = child
            if segments:
                node[segments[-1]] = _Leaf(namespace=entry.namespace, path=entry.path)

        self._mount_subtree(tree.root, root, depth=0)

    def _mount_subtree(self, parent_node, subtree: dict, depth: int) -> None:
        cap = self._max_depth
        # At the cap, render the next level as terminal leaves only — no
        # further recursion. ``cap == 0`` (All) disables the cap.
        terminal = cap and depth + 1 >= cap
        for label in sorted(subtree):
            value = subtree[label]
            if isinstance(value, _Leaf):
                parent_node.add_leaf(label, data=value)
            elif terminal:
                # Collapse the subtree at this point — no children mounted.
                parent_node.add_leaf(label)
            else:
                inner = parent_node.add(label, expand=True)
                self._mount_subtree(inner, value, depth + 1)

    def _filtered_memories(self) -> list[MemoryEntry]:
        # Outline is for user memories only — drop system namespaces.
        entries = [m for m in self._memories if m.namespace == "default"]

        def matches(path_lower: str, pattern: str) -> bool:
            """``*``/``?`` → fnmatch; otherwise substring. Both case-insensitive."""
            if "*" in pattern or "?" in pattern:
                return fnmatch.fnmatchcase(path_lower, pattern)
            return pattern in path_lower

        include = self._match_text
        exclude = self._exclude_text
        result: list[MemoryEntry] = []
        for m in entries:
            p = m.path.lower()
            if include and not matches(p, include):
                continue
            if exclude and matches(p, exclude):
                continue
            result.append(m)
        return result

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        leaf = event.node.data
        if not isinstance(leaf, _Leaf):
            return
        viewer = self.query_one(MemoryViewer)
        viewer.show(f"{leaf.path}\n\nLoading…", dim=True)
        # Cancel any in-flight body fetch so rapid arrow-navigation doesn't
        # paint stale content.
        if self._body_worker is not None and self._body_worker.state not in (
            WorkerState.SUCCESS,
            WorkerState.ERROR,
            WorkerState.CANCELLED,
        ):
            self._body_worker.cancel()
        self._body_worker = self.run_worker(
            self._fetch_body(leaf),
            exclusive=True,
            thread=True,
            description=f"outline:body:{leaf.namespace}:{leaf.path}",
        )

    def _fetch_body(self, leaf: _Leaf):
        def work():
            content = self._loader.get_memory(leaf.path, namespace=leaf.namespace)
            header = f"{leaf.path}\n\n"
            body = content if content is not None else "(empty)"
            self.app.call_from_thread(self.query_one(MemoryViewer).show, header + body)

        return work
