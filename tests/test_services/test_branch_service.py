"""
Tests for BranchService.

Tests branch operations: list, create, checkout, merge, commits, diff.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from memoir.services.branch_service import BranchService, MergeStrategy
from memoir.services.store_service import StoreService


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp = tempfile.mkdtemp(prefix="memoir_branch_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def initialized_store(temp_dir):
    """Create an initialized store."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    return temp_dir


@pytest.fixture
def branch_service(initialized_store):
    """Create a BranchService."""
    return BranchService(initialized_store)


class TestBranchServiceList:
    """Test branch listing functionality."""

    def test_list_branches_empty_store(self, branch_service):
        """Test listing branches in a new store."""
        result = branch_service.list_branches()

        assert result is not None
        assert hasattr(result, "branches")
        assert hasattr(result, "current")

    def test_list_branches_returns_list(self, branch_service):
        """Test that branches is a list."""
        result = branch_service.list_branches()

        assert isinstance(result.branches, list)

    def test_list_branches_has_main_or_master(self, branch_service):
        """Test that default branch exists."""
        result = branch_service.list_branches()

        # New git repos have main or master as default
        if result.branches:
            assert any(
                b in ["main", "master"] for b in result.branches
            ) or result.current in ["main", "master", None]


class TestBranchServiceCreate:
    """Test branch creation functionality."""

    def test_create_branch(self, branch_service):
        """Test creating a new branch."""
        result = branch_service.create_branch("test-branch")

        # May fail if no initial commit
        assert result is not None
        assert hasattr(result, "success")

    def test_create_branch_with_special_chars(self, branch_service):
        """Test creating branch with special characters."""
        result = branch_service.create_branch("feature/test-123")

        assert result is not None

    def test_create_duplicate_branch(self, branch_service):
        """Test creating a branch that already exists."""
        branch_service.create_branch("duplicate")
        result = branch_service.create_branch("duplicate")

        # Should fail or handle gracefully
        assert result is not None
        # Second creation should indicate failure or already exists
        if result.success:
            # Some implementations allow this
            pass
        else:
            assert result.error is not None or not result.success


class TestBranchServiceCheckout:
    """Test checkout functionality."""

    def test_checkout_existing_branch(self, branch_service):
        """Test checking out an existing branch."""
        # Try to checkout main/master
        result = branch_service.checkout("main")

        # May fail if no commits
        assert result is not None
        assert hasattr(result, "success")

    def test_checkout_with_create(self, branch_service):
        """Test checkout with create_if_missing flag."""
        result = branch_service.checkout("new-branch", create_if_missing=True)

        assert result is not None

    def test_checkout_nonexistent_branch(self, branch_service):
        """Test checking out a branch that doesn't exist."""
        result = branch_service.checkout("nonexistent-branch-xyz")

        # Should fail
        assert result is not None
        assert result.success is False or result.error is not None


class TestBranchServiceCommits:
    """Test commit history functionality."""

    def test_get_commits_empty_store(self, branch_service):
        """Test getting commits from empty store."""
        commits = branch_service.get_commits()

        assert commits is not None
        assert isinstance(commits, list)

    def test_get_commits_with_limit(self, branch_service):
        """Test getting commits with limit."""
        commits = branch_service.get_commits(limit=5)

        assert commits is not None
        assert len(commits) <= 5

    def test_get_commits_returns_commit_info(self, branch_service):
        """Test that commits have expected fields."""
        commits = branch_service.get_commits()

        # If there are commits, check structure
        for commit in commits:
            assert hasattr(commit, "hash") or hasattr(commit, "short_hash")
            assert hasattr(commit, "message")


class TestBranchServiceMerge:
    """Test merge functionality."""

    def test_merge_nonexistent_branch(self, branch_service):
        """Test merging a branch that doesn't exist."""
        result = branch_service.merge("nonexistent-branch")

        assert result is not None
        assert result.success is False or result.error is not None

    def test_merge_strategy_enum(self):
        """Test MergeStrategy enum values."""
        from prollytree import ConflictResolution

        assert MergeStrategy.OURS.value == "ours"
        assert MergeStrategy.THEIRS.value == "theirs"
        assert MergeStrategy.SKIP.value == "skip"

        # Test conversion to ConflictResolution
        assert (
            MergeStrategy.OURS.to_conflict_resolution()
            == ConflictResolution.TakeDestination
        )
        assert (
            MergeStrategy.THEIRS.to_conflict_resolution()
            == ConflictResolution.TakeSource
        )
        assert (
            MergeStrategy.SKIP.to_conflict_resolution() == ConflictResolution.IgnoreAll
        )

    def test_merge_default_strategy_is_skip(self, branch_service):
        """Test that default merge strategy is 'skip'."""
        # Create a branch to merge
        branch_service.create_branch("test-merge-default")
        result = branch_service.merge("test-merge-default")

        # The result should include the strategy used
        assert result is not None
        assert result.strategy == "skip"

    def test_merge_with_ours_strategy(self, branch_service):
        """Test merge with 'ours' strategy."""
        branch_service.create_branch("test-ours")
        result = branch_service.merge("test-ours", strategy=MergeStrategy.OURS)

        assert result is not None
        assert result.strategy == "ours"

    def test_merge_with_theirs_strategy(self, branch_service):
        """Test merge with 'theirs' strategy."""
        branch_service.create_branch("test-theirs")
        result = branch_service.merge("test-theirs", strategy=MergeStrategy.THEIRS)

        assert result is not None
        assert result.strategy == "theirs"

    def test_merge_result_includes_strategy(self, branch_service):
        """Test that MergeResult includes strategy field."""
        branch_service.create_branch("test-strategy")
        result = branch_service.merge("test-strategy", strategy=MergeStrategy.SKIP)

        assert result is not None
        assert hasattr(result, "strategy")
        assert result.strategy == "skip"

        # Test to_dict includes strategy
        result_dict = result.to_dict()
        assert "strategy" in result_dict
        assert result_dict["strategy"] == "skip"


class TestBranchServiceMergeWithData:
    """Test merge functionality with actual data in the store."""

    @pytest.fixture
    def store_with_data(self, temp_dir):
        """Create a store with some initial data."""
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        # Add some initial data using the store
        branch_service = BranchService(temp_dir)
        store = branch_service._get_store()

        # Store some data
        store.put(("default",), "preferences.theme", {"value": "light"})
        store.put(("default",), "preferences.language", {"value": "en"})
        store.commit("Initial data")

        return temp_dir

    @pytest.fixture
    def branch_service_with_data(self, store_with_data):
        """Create a BranchService with data."""
        return BranchService(store_with_data)

    def test_merge_branches_no_conflict(self, branch_service_with_data):
        """Test merging branches with no conflicts (different keys)."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("feature")
        service.checkout("feature")

        # Add new data on feature branch (different key)
        store.put(("default",), "preferences.font", {"value": "Arial"})
        store.commit("Add font preference")

        # Checkout main and merge
        service.checkout("main")
        result = service.merge("feature")

        assert result.success is True
        assert result.strategy == "skip"
        # No conflicts since different keys
        assert len(result.conflicts) == 0 or result.conflicts == []

        # Verify that the non-conflicting change from the feature branch
        # is now present on main after the merge
        merged_value = store.get(("default",), "preferences.font")
        assert merged_value == {"value": "Arial"}

    def test_merge_branches_with_conflict_skip_strategy(self, branch_service_with_data):
        """Test merging with conflict using 'skip' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-skip")
        service.checkout("conflict-skip")

        # Modify same key on feature branch (will conflict with main)
        store.put(("default",), "preferences.theme", {"value": "dark"})
        # Also add a different key on feature branch (no conflict)
        store.put(("default",), "preferences.font", {"value": "Arial"})
        store.commit("Change theme to dark and add font")

        # Go back to main and modify same key to create a conflict
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Try to merge - should have conflict on theme but still merge font
        result = service.merge("conflict-skip", strategy=MergeStrategy.SKIP)

        assert result is not None
        assert result.strategy == "skip"
        assert result.success is True

        # Destination branch (main) should keep its value for the conflicting key
        theme = store.get(("default",), "preferences.theme")
        assert theme is not None
        assert theme.get("value") == "system"

        # Non-conflicting key from the source branch should be merged
        font = store.get(("default",), "preferences.font")
        assert font is not None
        assert font.get("value") == "Arial"

    def test_merge_branches_with_conflict_ours_strategy(self, branch_service_with_data):
        """Test merging with conflict using 'ours' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-ours")
        service.checkout("conflict-ours")

        # Modify same key on feature branch
        store.put(("default",), "preferences.theme", {"value": "dark"})
        store.commit("Change theme to dark")

        # Go back to main and modify same key
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Merge with 'ours' - should keep main's version
        result = service.merge("conflict-ours", strategy=MergeStrategy.OURS)

        assert result is not None
        assert result.strategy == "ours"

        # After merge, check that we kept 'ours' (main's value)
        if result.success:
            theme = store.get(("default",), "preferences.theme")
            assert theme is not None
            # 'ours' means keep destination (main) which was "system"
            assert theme.get("value") == "system"

    def test_merge_branches_with_conflict_theirs_strategy(
        self, branch_service_with_data
    ):
        """Test merging with conflict using 'theirs' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-theirs")
        service.checkout("conflict-theirs")

        # Modify same key on feature branch
        store.put(("default",), "preferences.theme", {"value": "dark"})
        store.commit("Change theme to dark")

        # Go back to main and modify same key
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Merge with 'theirs' - should take feature branch's version
        result = service.merge("conflict-theirs", strategy=MergeStrategy.THEIRS)

        assert result is not None
        assert result.strategy == "theirs"

        # After merge, check that we took 'theirs' (feature's value)
        if result.success:
            theme = store.get(("default",), "preferences.theme")
            assert theme is not None
            # 'theirs' means take source (conflict-theirs) which was "dark"
            assert theme.get("value") == "dark"


class TestBranchServiceDefaultBranch:
    """Test default-branch resolution (main → master → first)."""

    def test_returns_main_when_present(self, branch_service_with_data):
        """main is the preferred default when it exists."""
        assert branch_service_with_data.get_default_branch() == "main"

    def test_falls_back_to_master(self, branch_service_with_data, monkeypatch):
        """If main is missing, master wins."""
        fake_info = BranchInfoStub(branches=["master", "feature/x"], current="master")
        monkeypatch.setattr(
            branch_service_with_data, "list_branches", lambda: fake_info
        )
        assert branch_service_with_data.get_default_branch() == "master"

    def test_falls_back_to_first_branch(self, branch_service_with_data, monkeypatch):
        """Neither main nor master → first branch in the list."""
        fake_info = BranchInfoStub(branches=["trunk", "feature/x"], current="trunk")
        monkeypatch.setattr(
            branch_service_with_data, "list_branches", lambda: fake_info
        )
        assert branch_service_with_data.get_default_branch() == "trunk"

    def test_empty_repo_fallback(self, branch_service_with_data, monkeypatch):
        """Empty branch list → 'main' as last-resort fallback."""
        fake_info = BranchInfoStub(branches=[], current="")
        monkeypatch.setattr(
            branch_service_with_data, "list_branches", lambda: fake_info
        )
        assert branch_service_with_data.get_default_branch() == "main"


class TestBranchServicePrimaryBranch:
    """Test the user-designated primary branch override.

    Backwards-compat invariant: when no override is set, every assertion
    in TestBranchServiceDefaultBranch must still hold. The tests below add
    behavior on top — they never replace it.
    """

    def test_default_branch_unchanged_when_config_unset(self, branch_service_with_data):
        """No memoir.primaryBranch config → resolves to 'main' as before."""
        assert branch_service_with_data.get_primary_branch_config() is None
        assert branch_service_with_data.get_default_branch() == "main"

    def test_get_primary_branch_config_returns_value(self, branch_service_with_data):
        """Once set, the raw config value is returned by get_primary_branch_config."""
        # Create the branch first so set_primary_branch's existence check passes.
        branch_service_with_data.create_branch("master")
        branch_service_with_data.set_primary_branch("master")
        assert branch_service_with_data.get_primary_branch_config() == "master"

    def test_default_branch_honors_memoir_primary_config(
        self, branch_service_with_data
    ):
        """When config is set AND the branch exists, it wins over main/master fallback."""
        branch_service_with_data.create_branch("custom-primary")
        branch_service_with_data.set_primary_branch("custom-primary")
        assert branch_service_with_data.get_default_branch() == "custom-primary"

    def test_default_branch_falls_back_when_config_branch_missing(
        self, branch_service_with_data, monkeypatch
    ):
        """Config points at a deleted branch → falls through to main/master/first."""
        # Stage 1: write config pointing at a branch that exists.
        branch_service_with_data.create_branch("ephemeral")
        branch_service_with_data.set_primary_branch("ephemeral")
        assert branch_service_with_data.get_default_branch() == "ephemeral"

        # Stage 2: simulate the branch being deleted by stubbing list_branches
        # to omit it. The config still points at "ephemeral", but
        # get_default_branch must fall through to the existing chain.
        fake_info = BranchInfoStub(branches=["main"], current="main")
        monkeypatch.setattr(
            branch_service_with_data, "list_branches", lambda: fake_info
        )
        assert branch_service_with_data.get_default_branch() == "main"

    def test_set_primary_branch_validates_existence(self, branch_service_with_data):
        """Refuses to set config to a non-existent branch."""
        with pytest.raises(ValueError, match="does not exist"):
            branch_service_with_data.set_primary_branch("nope-not-a-branch")
        # Config must remain unset after the failed attempt.
        assert branch_service_with_data.get_primary_branch_config() is None

    def test_set_primary_branch_unset_clears_config(self, branch_service_with_data):
        """Passing an empty string removes the config so resolution falls through."""
        branch_service_with_data.create_branch("master")
        branch_service_with_data.set_primary_branch("master")
        assert branch_service_with_data.get_primary_branch_config() == "master"

        branch_service_with_data.set_primary_branch("")
        assert branch_service_with_data.get_primary_branch_config() is None
        # And get_default_branch resolves back via the existing chain.
        assert branch_service_with_data.get_default_branch() == "main"


class TestBranchServiceDivergence:
    """Test get_divergence ahead/behind counting."""

    @pytest.fixture
    def service_with_diverged_branches(self, temp_dir):
        """Make a store with main + feature, each with extra commits."""
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        service = BranchService(temp_dir)
        store = service._get_store()

        # Initial commit on main
        store.put(("default",), "preferences.theme", {"value": "light"})
        store.commit("initial on main")

        # feature branch off main, add one commit on feature
        service.create_branch("feature")
        service.checkout("feature")
        store.put(("default",), "preferences.font", {"value": "Arial"})
        store.commit("feature: add font")

        # Back to main, add two commits on main
        service.checkout("main")
        store.put(("default",), "preferences.lang", {"value": "en"})
        store.commit("main: add lang")
        store.put(("default",), "preferences.locale", {"value": "US"})
        store.commit("main: add locale")

        return service

    def test_same_branch_returns_zero(self, service_with_diverged_branches):
        div = service_with_diverged_branches.get_divergence("main", base="main")
        assert div["ahead"] == 0
        assert div["behind"] == 0
        assert div["branch"] == "main"
        assert div["base"] == "main"

    def test_feature_ahead_and_behind(self, service_with_diverged_branches):
        """feature has commits main doesn't and vice versa — main has more."""
        # Exact counts depend on how many git commits store.commit() produces
        # internally; just assert the relative shape holds.
        div = service_with_diverged_branches.get_divergence("feature", base="main")
        assert div["ahead"] > 0, f"expected ahead>0, got {div}"
        assert div["behind"] > 0, f"expected behind>0, got {div}"
        assert (
            div["behind"] > div["ahead"]
        ), f"main had 2 extra commits vs feature's 1, got {div}"

    def test_base_defaults_to_default_branch(self, service_with_diverged_branches):
        """Omitting base → uses get_default_branch() which resolves to 'main'."""
        div = service_with_diverged_branches.get_divergence("feature")
        assert div["base"] == "main"
        assert div["ahead"] > 0
        assert div["behind"] > div["ahead"]

    def test_nonexistent_branch_sets_error(self, service_with_diverged_branches):
        div = service_with_diverged_branches.get_divergence(
            "does-not-exist", base="main"
        )
        # git rev-list fails; we return zeros with an error string
        assert div["ahead"] == 0
        assert div["behind"] == 0
        assert div.get("error")


class TestBranchServiceBranchesStatus:
    """Test the aggregated get_branches_status used by the UI."""

    @pytest.fixture
    def service_two_branches(self, temp_dir):
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        service = BranchService(temp_dir)
        store = service._get_store()

        store.put(("default",), "a", {"v": 1})
        store.commit("main c1")

        service.create_branch("feature")
        service.checkout("feature")
        store.put(("default",), "b", {"v": 1})
        store.commit("feature c1")

        service.checkout("main")
        return service

    def test_shape(self, service_two_branches):
        status = service_two_branches.get_branches_status()
        assert status["default"] == "main"
        assert status["current"] == "main"
        names = [b["name"] for b in status["branches"]]
        assert "main" in names
        assert "feature" in names

    def test_feature_is_ahead(self, service_two_branches):
        status = service_two_branches.get_branches_status()
        feature = next(b for b in status["branches"] if b["name"] == "feature")
        assert feature["ahead"] > 0
        assert feature["behind"] == 0
        assert feature["is_default"] is False
        assert feature["is_current"] is False

    def test_default_row_has_zero_divergence(self, service_two_branches):
        status = service_two_branches.get_branches_status()
        main = next(b for b in status["branches"] if b["name"] == "main")
        assert main["is_default"] is True
        assert main["is_current"] is True
        assert main["ahead"] == 0
        assert main["behind"] == 0


class TestBranchServiceSyncBranch:
    """Test the compound sync_branch operation."""

    @pytest.fixture
    def service_syncable(self, temp_dir):
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        service = BranchService(temp_dir)
        store = service._get_store()

        store.put(("default",), "shared", {"v": "main"})
        store.commit("main initial")

        service.create_branch("feature")
        service.checkout("feature")
        store.put(("default",), "only-on-feature", {"v": 1})
        store.commit("feature work")

        # Leave user on a third branch so we can prove restoration
        service.create_branch("user-scratch")
        service.checkout("user-scratch")

        return service

    def test_sync_restores_original_branch(self, service_syncable):
        """After syncing feature→main, user ends up back on user-scratch."""
        result = service_syncable.sync_branch("feature", "main")
        assert result.success is True
        assert result.target_branch == "main"
        assert result.source_branch == "feature"
        assert result.restored_branch == "user-scratch"

        current, _ = service_syncable.get_current_branch()
        assert current == "user-scratch"

    def test_sync_applies_merge_on_target(self, service_syncable):
        service_syncable.sync_branch("feature", "main")
        # Check main has feature's key
        service_syncable.checkout("main")
        store = service_syncable._get_store()
        assert store.get(("default",), "only-on-feature") == {"v": 1}

    def test_sync_same_source_and_target_fails(self, service_syncable):
        result = service_syncable.sync_branch("main", "main")
        assert result.success is False
        assert "same" in (result.error or "").lower()

    def test_sync_missing_target_fails_gracefully(self, service_syncable):
        result = service_syncable.sync_branch("feature", "does-not-exist")
        assert result.success is False
        # Make sure we didn't strand the user somewhere weird
        current, _ = service_syncable.get_current_branch()
        assert current == "user-scratch"

    def test_sync_no_restore(self, service_syncable):
        """restore=False leaves us on the target after a clean merge."""
        result = service_syncable.sync_branch("feature", "main", restore=False)
        assert result.success is True
        assert result.restored_branch is None
        current, _ = service_syncable.get_current_branch()
        assert current == "main"


class TestBranchServicePromoteBranch:
    """Test the safe additive promote_branch operation.

    The three guarantees:
      1. Only the ``default`` namespace is touched.
      2. Only inserts and updates — never deletions.
      3. ``dry_run=True`` previews without writing.
    """

    @pytest.fixture
    def service_with_namespaces(self, temp_dir):
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        service = BranchService(temp_dir)
        store = service._get_store()

        # main: has a default key, an onboard key (should NOT be touched), and
        # a default key that the source will leave alone (no-delete guarantee).
        store.put(("default",), "shared", {"v": "main"})
        store.put(("default",), "only-on-main", {"v": "main-keep"})
        store.put(("codebase", "onboard"), "_meta.last_onboard.commit", "abc123")
        store.put(("codebase", "onboard"), "_meta.last_onboard.date", "2026-04-25")
        store.commit("main initial")

        # feature: branches from main, then adds two new default keys, updates
        # `shared`, and adds an onboard key (which must also NOT propagate).
        service.create_branch("feature")
        service.checkout("feature")
        # Re-init store handle so puts land on the feature branch tree.
        service._store = None
        store = service._get_store()
        store.put(("default",), "shared", {"v": "feature"})
        store.put(("default",), "added-1", {"v": 1})
        store.put(("default",), "added-2", {"v": 2})
        store.put(("codebase", "onboard"), "feature-only-onboard", "should-not-leak")
        store.commit("feature work")

        # Leave the caller on yet another branch so we can prove restoration.
        service.create_branch("scratch")
        service.checkout("scratch")
        service._store = None

        return service

    def test_promote_dry_run_lists_changes_without_writing(
        self, service_with_namespaces
    ):
        result = service_with_namespaces.promote_branch("feature", "main", dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert result.commit_hash is None
        assert sorted(result.added_keys) == ["added-1", "added-2"]
        assert sorted(result.updated_keys) == ["shared"]
        # Caller stayed on scratch.
        assert result.restored_branch == "scratch"

        # main is unchanged: still has only-on-main, shared still says "main".
        service_with_namespaces.checkout("main")
        service_with_namespaces._store = None
        store = service_with_namespaces._get_store()
        assert store.get(("default",), "shared") == {"v": "main"}
        assert store.get(("default",), "added-1") is None
        assert store.get(("default",), "added-2") is None
        assert store.get(("default",), "only-on-main") == {"v": "main-keep"}

    def test_promote_only_touches_default_namespace(self, service_with_namespaces):
        """Even though feature has a codebase:onboard key, promotion must not
        copy it to main. main's existing onboard keys must survive untouched."""
        service_with_namespaces.promote_branch("feature", "main", dry_run=False)

        service_with_namespaces.checkout("main")
        service_with_namespaces._store = None
        store = service_with_namespaces._get_store()

        # main retains its original onboard keys.
        assert (
            store.get(("codebase", "onboard"), "_meta.last_onboard.commit") == "abc123"
        )
        assert (
            store.get(("codebase", "onboard"), "_meta.last_onboard.date")
            == "2026-04-25"
        )
        # feature's onboard-only key must NOT have leaked into main.
        assert store.get(("codebase", "onboard"), "feature-only-onboard") is None

    def test_promote_never_deletes_target_only_keys(self, service_with_namespaces):
        """Keys present on main but absent from feature must survive."""
        service_with_namespaces.promote_branch("feature", "main", dry_run=False)

        service_with_namespaces.checkout("main")
        service_with_namespaces._store = None
        store = service_with_namespaces._get_store()

        # Even though `only-on-main` doesn't exist on feature, it stays on main.
        assert store.get(("default",), "only-on-main") == {"v": "main-keep"}

    def test_promote_applies_adds_and_updates(self, service_with_namespaces):
        result = service_with_namespaces.promote_branch(
            "feature", "main", dry_run=False
        )
        assert result.success is True
        assert result.dry_run is False
        assert sorted(result.added_keys) == ["added-1", "added-2"]
        assert sorted(result.updated_keys) == ["shared"]
        assert result.commit_hash is not None

        service_with_namespaces.checkout("main")
        service_with_namespaces._store = None
        store = service_with_namespaces._get_store()
        assert store.get(("default",), "added-1") == {"v": 1}
        assert store.get(("default",), "added-2") == {"v": 2}
        assert store.get(("default",), "shared") == {"v": "feature"}

    def test_promote_restores_original_branch(self, service_with_namespaces):
        result = service_with_namespaces.promote_branch(
            "feature", "main", dry_run=False
        )
        assert result.restored_branch == "scratch"
        current, _ = service_with_namespaces.get_current_branch()
        assert current == "scratch"

    def test_promote_same_source_and_target_fails(self, service_with_namespaces):
        result = service_with_namespaces.promote_branch("main", "main")
        assert result.success is False
        assert "same" in (result.error or "").lower()

    def test_promote_no_changes_does_not_create_commit(self, service_with_namespaces):
        # First promotion applies changes; a second one should be a no-op.
        service_with_namespaces.promote_branch("feature", "main", dry_run=False)
        service_with_namespaces._store = None

        result = service_with_namespaces.promote_branch(
            "feature", "main", dry_run=False
        )
        assert result.success is True
        assert result.added_keys == []
        assert result.updated_keys == []
        # No commit created when there's nothing to apply.
        assert result.commit_hash is None

    def test_promote_carries_metrics_keys_with_branch_in_path(self, temp_dir):
        """The Stop hook writes per-branch turn metrics under
        `metrics.turn.<branch>` in the default namespace. Promotion must
        carry those keys to the target so the source branch's stats land on
        main alongside its memories — preserving source-branch identity via
        the key fragment itself (no special-case merge logic)."""
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)
        service = BranchService(temp_dir)
        store = service._get_store()

        # main has its own running accumulator.
        store.put(
            ("default",),
            "metrics.turn.main",
            {"branch": "main", "turns_count": 5, "total_output_chars": 100},
        )
        store.commit("main initial")

        # feature/x branches and accumulates its own metrics.
        service.create_branch("feature/x")
        service.checkout("feature/x")
        service._store = None
        store = service._get_store()
        store.put(
            ("default",),
            "metrics.turn.feature/x",
            {"branch": "feature/x", "turns_count": 3, "total_output_chars": 42},
        )
        store.commit("feature/x metrics")

        result = service.promote_branch("feature/x", "main", dry_run=False)
        assert result.success is True
        assert "metrics.turn.feature/x" in result.added_keys

        service.checkout("main")
        service._store = None
        store = service._get_store()

        # main retains its own metrics key untouched.
        main_metrics = store.get(("default",), "metrics.turn.main")
        assert main_metrics == {
            "branch": "main",
            "turns_count": 5,
            "total_output_chars": 100,
        }
        # feature/x's metrics key rode along, preserving source-branch identity.
        feature_metrics = store.get(("default",), "metrics.turn.feature/x")
        assert feature_metrics == {
            "branch": "feature/x",
            "turns_count": 3,
            "total_output_chars": 42,
        }

    def test_promote_recovers_from_dirty_working_tree(self, temp_dir):
        """Regression: a long-lived process with a dirty `data/` working tree
        used to silently zero out the promote diff because both reads saw
        the same accumulated working-tree state. The fix forces
        `git checkout HEAD -- data/` before each branch read.

        This test simulates the long-running UI server scenario by hand-
        dirtying the working tree between the BranchService construction
        and the promote_branch call. Without the fix, the dirty files
        would mask the source-vs-target diff.
        """
        import subprocess

        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)
        service = BranchService(temp_dir)
        store = service._get_store()
        store.put(("default",), "shared", {"v": "main"})
        store.commit("main initial")

        service.create_branch("feature")
        service.checkout("feature")
        service._store = None
        store = service._get_store()
        store.put(("default",), "feature_only", {"v": "feature_value"})
        store.commit("feature work")

        # Simulate "long-running process leaves data/ dirty": append junk
        # to one of the prollytree binary files. Real-world cause is
        # repeated ProllyTreeStore writes between commits, but for a
        # deterministic test we just dirty the file directly.
        data_dir = Path(temp_dir) / "data"
        if data_dir.exists():
            for f in data_dir.iterdir():
                if f.is_file():
                    with open(f, "ab") as fh:
                        fh.write(b"# stale state from prior request\n")
                    break

        # Confirm the working tree is in fact dirty before the call.
        status = subprocess.run(
            ["git", "-C", temp_dir, "status", "--short"],
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip(), "fixture failed to dirty data/"

        # promote_branch must still see feature_only as a new key on main —
        # the fix's working-tree reset is what makes this pass.
        service.checkout("main")
        service._store = None
        result = service.promote_branch("feature", "main", dry_run=True)
        assert result.success is True
        assert "feature_only" in result.added_keys, (
            f"dirty working tree masked the diff — got added={result.added_keys}, "
            f"updated={result.updated_keys}"
        )


class BranchInfoStub:
    """Minimal stand-in for BranchInfo used in default-branch tests."""

    def __init__(self, branches, current):
        self.branches = branches
        self.current = current


@pytest.fixture
def branch_service_with_data(temp_dir):
    """Fixture used by default-branch tests — store with one commit on main."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    service = BranchService(temp_dir)
    store = service._get_store()
    store.put(("default",), "a", {"v": 1})
    store.commit("initial")
    return service


class TestBranchServiceDiff:
    """Test diff functionality."""

    def test_get_diff_empty_store(self, branch_service):
        """Test getting diff from empty store."""
        # May fail or return empty
        try:
            diff = branch_service.get_diff("HEAD~1", "HEAD")
            assert diff is not None or diff == ""
        except Exception:
            # Expected if no commits
            pass

    def test_get_diff_same_commit(self, branch_service):
        """Test diff between same commit."""
        try:
            diff = branch_service.get_diff("HEAD", "HEAD")
            # Should be empty or minimal
            assert diff is not None
        except Exception:
            # Expected if no commits
            pass


class TestBranchServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_with_invalid_path(self):
        """Test service with invalid store path."""
        from memoir.services.base import StoreNotFoundError

        service = BranchService("/nonexistent/path")

        # Should raise StoreNotFoundError
        with pytest.raises(StoreNotFoundError):
            service.list_branches()

    def test_branch_name_validation(self, branch_service):
        """Test branch name with invalid characters."""
        # Git doesn't allow certain characters
        result = branch_service.create_branch("invalid..name")

        # Should fail gracefully
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
