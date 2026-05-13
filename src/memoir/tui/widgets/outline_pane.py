# SPDX-License-Identifier: Apache-2.0
"""OutlinePane — split layout: filter + Tree of memories | MemoryViewer.

Tree shape: dotted-path segments of every memory in the ``default``
namespace. System namespaces (``codebase:onboard``, ``taxonomy``,
``project:onboard``, etc.) are hidden — the outline is for user memories
only. Substring filter (case-insensitive) hides non-matching paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Tree
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


class OutlinePane(Vertical):
    DEFAULT_CSS = """
    OutlinePane > Input {
        height: 3;
        margin: 0;
    }
    OutlinePane > Horizontal {
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
        Binding("slash", "focus_filter", "Filter", show=True),
    ]

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader
        self._memories: list[MemoryEntry] = []
        self._loaded = False
        self._load_worker: Worker | None = None
        self._body_worker: Worker | None = None
        self._filter_text = ""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="filter…  (substring, case-insensitive)", id="outline-filter"
        )
        with Horizontal():
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
    # Filter
    # ------------------------------------------------------------------

    def action_focus_filter(self) -> None:
        self.query_one("#outline-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "outline-filter":
            return
        self._filter_text = event.value.strip().lower()
        self._rebuild_tree()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing enter inside the filter input shifts focus to the tree.
        if event.input.id == "outline-filter":
            self.query_one(Tree).focus()

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
        # group since we already filtered to default-only.
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

        self._mount_subtree(tree.root, root)

    def _mount_subtree(self, parent_node, subtree: dict) -> None:
        for label in sorted(subtree):
            value = subtree[label]
            if isinstance(value, _Leaf):
                parent_node.add_leaf(label, data=value)
            else:
                inner = parent_node.add(label, expand=True)
                self._mount_subtree(inner, value)

    def _filtered_memories(self) -> list[MemoryEntry]:
        # Outline is for user memories only — drop system namespaces.
        entries = [m for m in self._memories if m.namespace == "default"]
        if not self._filter_text:
            return entries
        needle = self._filter_text
        return [m for m in entries if needle in m.path.lower()]

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
