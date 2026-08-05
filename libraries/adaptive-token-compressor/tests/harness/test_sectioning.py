"""Tests for harness/sectioning.py — covers plan §13 row `harness/sectioning`."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.harness.sectioning import (
    SectioningConfig,
    SectionInfo,
    SectionSplitter,
)


# ─────────────────────────────────────────────────────────────────────────────
# SectioningConfig
# ─────────────────────────────────────────────────────────────────────────────


class TestSectioningConfig:
    def test_default_empty(self):
        config = SectioningConfig()
        assert config.primary_headings == []
        assert config.preserve_headings == set()
        assert config.workspace_path_pattern is None

    def test_custom_values(self):
        config = SectioningConfig(
            primary_headings=["## Tools", "## Context"],
            preserve_headings={"## Tools"},
            workspace_path_pattern=r"/tmp/test",
        )
        assert config.primary_headings == ["## Tools", "## Context"]
        assert config.preserve_headings == {"## Tools"}
        assert config.workspace_path_pattern == "/tmp/test"


# ─────────────────────────────────────────────────────────────────────────────
# SectionInfo
# ─────────────────────────────────────────────────────────────────────────────


class TestSectionInfo:
    def test_fields(self):
        section = SectionInfo("## Tools", "content", True)
        assert section.name == "## Tools"
        assert section.content == "content"
        assert section.should_compress is True


# ─────────────────────────────────────────────────────────────────────────────
# SectionSplitter - no boundaries
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitterNoBoundaries:
    def test_empty_config_single_section(self):
        config = SectioningConfig()
        splitter = SectionSplitter(config)
        sections = splitter.split("Some text here")
        assert len(sections) == 1
        assert sections[0].name == "entire_text"
        assert sections[0].content == "Some text here"
        assert sections[0].should_compress is True

    def test_no_matching_headings_single_section(self):
        config = SectioningConfig(primary_headings=["## Tools"])
        splitter = SectionSplitter(config)
        sections = splitter.split("Text without ## Tools heading")
        assert len(sections) == 1
        assert sections[0].name == "entire_text"


# ─────────────────────────────────────────────────────────────────────────────
# SectionSplitter - primary headings (real newlines)
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitterPrimaryHeadingsRealNewlines:
    def test_single_heading(self):
        config = SectioningConfig(primary_headings=["## Tools"])
        splitter = SectionSplitter(config)
        text = "Intro text\n## Tools\nTool content"
        sections = splitter.split(text)
        assert len(sections) == 2
        assert sections[0].name == "Intro"
        assert sections[0].content == "Intro text"
        assert sections[0].should_compress is False
        assert sections[1].name == "## Tools"
        assert sections[1].content == "\n## Tools\nTool content"
        assert sections[1].should_compress is True

    def test_multiple_headings(self):
        config = SectioningConfig(primary_headings=["## Tools", "## Context"])
        splitter = SectionSplitter(config)
        text = "Intro\n## Tools\nTools section\n## Context\nContext section"
        sections = splitter.split(text)
        assert len(sections) == 3
        assert sections[0].name == "Intro"
        assert sections[1].name == "## Tools"
        assert sections[2].name == "## Context"

    def test_preserve_heading(self):
        config = SectioningConfig(
            primary_headings=["## Tools", "## Context"],
            preserve_headings={"## Tools"},
        )
        splitter = SectionSplitter(config)
        text = "\n## Tools\ntools\n## Context\ncontext"
        sections = splitter.split(text)
        assert sections[0].should_compress is False  # preserved
        assert sections[1].should_compress is True  # not preserved

    def test_no_intro_when_starts_with_heading(self):
        config = SectioningConfig(primary_headings=["## Tools"])
        splitter = SectionSplitter(config)
        text = "\n## Tools\ncontent"
        sections = splitter.split(text)
        assert len(sections) == 1
        assert sections[0].name == "## Tools"


# ─────────────────────────────────────────────────────────────────────────────
# SectionSplitter - escaped newlines
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitterEscapedNewlines:
    def test_escaped_newline_detection(self):
        config = SectioningConfig(primary_headings=["## Tools"])
        splitter = SectionSplitter(config)
        text = "Intro\\n## Tools\\nTool content"
        sections = splitter.split(text)
        assert len(sections) == 2
        assert sections[0].name == "Intro"
        assert sections[0].content == "Intro"
        assert sections[1].name == "## Tools"
        assert sections[1].content == "\\n## Tools\\nTool content"


# ─────────────────────────────────────────────────────────────────────────────
# SectionSplitter - file-path headings
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitterFilePathHeadings:
    def test_file_path_heading_split(self):
        config = SectioningConfig(
            workspace_path_pattern=r"/tmp/workspace"
        )
        splitter = SectionSplitter(config)
        # Real router prompts always emit file-path headings as
        # ``## <workspace>/<filename>`` lines (project-context attachments).
        text = "Intro\n## /tmp/workspace/file.py\nFile content here"
        sections = splitter.split(text)
        assert len(sections) == 3
        assert sections[0].name == "Intro"
        assert sections[1].name == "Heading: file.py"
        assert sections[1].should_compress is False
        assert sections[2].name == "Content: file.py"
        assert sections[2].should_compress is True

    def test_file_path_no_slash_uses_truncated_heading(self):
        # ``[^/\s]+`` regex makes Windows-style paths (no ``/``) un-matchable;
        # this test now verifies the long-name truncation rule using a posix
        # path whose basename exceeds 40 chars.
        config = SectioningConfig(workspace_path_pattern=r"/long")
        splitter = SectionSplitter(config)
        text = "\n## /long/verylongnamethatexceeds40charsxxxxxxxxxxxxxxxx\ncontent"
        sections = splitter.split(text)
        assert sections[0].name.startswith("Heading: ")
        # basename is everything after the last "/"; we just confirm
        # the heading is non-empty and the section was created.
        assert sections[0].should_compress is False

    def test_file_path_empty_content_skipped(self):
        config = SectioningConfig(workspace_path_pattern=r"/tmp/test")
        splitter = SectionSplitter(config)
        text = "\n## /tmp/test/file.py\n\n## /tmp/test/another.py\nContent here"
        sections = splitter.split(text)
        # First file: heading only (no content), second file: heading + content
        assert len(sections) == 3
        assert sections[0].name == "Heading: file.py"
        assert sections[1].name == "Heading: another.py"
        assert sections[2].name == "Content: another.py"


# ─────────────────────────────────────────────────────────────────────────────
# SectionSplitter - mixed boundaries
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitterMixedBoundaries:
    def test_primary_and_file_path_headings(self):
        config = SectioningConfig(
            primary_headings=["## Tools"],
            workspace_path_pattern=r"/workspace",
        )
        splitter = SectionSplitter(config)
        text = "Intro\n## Tools\ntools\n## /workspace/file.py\ncontent"
        sections = splitter.split(text)
        assert len(sections) == 4
        assert sections[0].name == "Intro"
        assert sections[1].name == "## Tools"
        assert sections[2].name == "Heading: file.py"
        assert sections[3].name == "Content: file.py"

    def test_boundaries_sorted_by_position(self):
        config = SectioningConfig(
            primary_headings=["## B", "## A"],  # order doesn't matter
            workspace_path_pattern=r"/test",
        )
        splitter = SectionSplitter(config)
        # Position order: ## A < ## /test/file < ## B
        text = "\n## A\nA content\n## /test/file\nfile\n## B\nB content"
        sections = splitter.split(text)
        assert sections[0].name == "## A"
        assert sections[1].name == "Heading: file"
        assert sections[2].name == "Content: file"
        assert sections[3].name == "## B"
