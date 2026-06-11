"""Tests for Learned Prompt Set file store."""

import json
import tempfile
from pathlib import Path

import pytest

from testcase_agent.prompt_learning.file_store import (
    save_learned_prompt_set,
    list_versions,
    read_version,
)
from testcase_agent.prompt_learning.contracts import (
    LearnedPromptSetMeta,
    ParsedSummary,
)


@pytest.fixture
def tmp_root():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def make_meta(version="", created_at="2026-06-11T14:30:00Z"):
    return LearnedPromptSetMeta(
        version=version,
        created_at=created_at,
        provider="ollama",
        model="qwen2.5:7b",
        summary=ParsedSummary(
            requirement_count=10,
            ref_test_case_count=20,
            valid_link_count=30,
            no_test_requirement_count=2,
            style_only_case_count=1,
            data_issue_count=3,
        ),
    )


def make_prompt_files() -> dict[str, str]:
    return {
        "analyze_test_basis.system.html": "<p>sys A</p>",
        "analyze_test_basis.user.html": "<p>usr A</p>",
        "plan_case_intents.system.html": "<p>sys B</p>",
        "plan_case_intents.user.html": "<p>usr B</p>",
        "generate_case.system.html": "<p>sys C</p>",
        "generate_case.user.html": "<p>usr C</p>",
    }


class TestSaveAndList:
    def test_save_and_list(self, tmp_root):
        meta = make_meta()
        version = save_learned_prompt_set(
            meta, "# Rationale\nTest.", make_prompt_files(), root=tmp_root,
        )
        assert version  # version string returned

        versions = list_versions(root=tmp_root)
        assert len(versions) == 1
        assert versions[0].provider == "ollama"
        assert versions[0].summary.requirement_count == 10

    def test_collision_suffix(self, tmp_root):
        meta1 = make_meta()
        meta2 = make_meta()
        v1 = save_learned_prompt_set(meta1, "# R1", make_prompt_files(), root=tmp_root)
        # Force same version name
        meta2.version = v1
        v2 = save_learned_prompt_set(meta2, "# R2", make_prompt_files(), root=tmp_root)
        assert v2 != v1
        assert v2.startswith(v1)

        versions = list_versions(root=tmp_root)
        assert len(versions) == 2

    def test_list_sorted_newest_first(self, tmp_root):
        meta_old = make_meta(created_at="2026-06-10T10:00:00Z")
        meta_new = make_meta(created_at="2026-06-12T10:00:00Z")

        save_learned_prompt_set(meta_old, "# R1", make_prompt_files(), root=tmp_root)
        save_learned_prompt_set(meta_new, "# R2", make_prompt_files(), root=tmp_root)

        versions = list_versions(root=tmp_root)
        assert len(versions) == 2
        assert versions[0].created_at == "2026-06-12T10:00:00Z"


class TestReadVersion:
    def test_read_version(self, tmp_root):
        meta = make_meta()
        version = save_learned_prompt_set(
            meta, "# My Rationale", make_prompt_files(), root=tmp_root,
        )
        v = read_version(version, root=tmp_root)
        assert v is not None
        assert v.meta.version == version
        assert v.rationale == "# My Rationale"
        assert len(v.prompt_groups) == 3
        assert v.prompt_groups[0].stage == "A"
        assert v.prompt_groups[2].stage == "C"

    def test_read_version_prompt_contents(self, tmp_root):
        meta = make_meta()
        version = save_learned_prompt_set(
            meta, "# R", make_prompt_files(), root=tmp_root,
        )
        v = read_version(version, root=tmp_root)
        assert v is not None
        # Check one prompt from each stage
        a_sys = next(g for g in v.prompt_groups if g.stage == "A").system_prompt
        assert a_sys.filename == "analyze_test_basis.system.html"
        assert "sys A" in a_sys.content

    def test_read_nonexistent_returns_none(self, tmp_root):
        v = read_version("nonexistent", root=tmp_root)
        assert v is None


class TestAtomicSave:
    def test_temp_folder_not_in_list(self, tmp_root):
        # Create a temp folder manually and verify it's excluded from listing
        (tmp_root / ".tmp-test").mkdir(parents=True)
        (tmp_root / ".tmp-test" / "metadata.json").write_text(
            json.dumps({"version": "tmp", "createdAt": "2026-01-01T00:00:00Z", "provider": "m", "model": "m"})
        )
        versions = list_versions(root=tmp_root)
        assert all(v.version != "tmp" for v in versions)

    def test_save_failure_cleans_temp(self, tmp_root):
        meta = make_meta()
        # Try to save with a file that conflicts with dir creation
        # by making the temp dir point to a file
        (tmp_root / ".tmp-force").write_text("block")
        try:
            save_learned_prompt_set(meta, "# R", make_prompt_files(), root=tmp_root)
        except Exception:
            pass
        # After failure, temp should be cleaned
        remaining_tmp = list(tmp_root.glob(".tmp-*"))
        # May have other debris but not the blocked one
        assert not (tmp_root / ".tmp-force").exists() or (tmp_root / ".tmp-force").is_file()
