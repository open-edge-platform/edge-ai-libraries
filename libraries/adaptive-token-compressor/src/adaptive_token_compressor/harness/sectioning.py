# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Section splitter: cut a system/developer prompt at heading boundaries."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectioningConfig:
    primary_headings: list[str] = field(default_factory=list)
    preserve_headings: set[str] = field(default_factory=set)
    workspace_path_pattern: str | None = None


@dataclass(frozen=True)
class SectionInfo:
    name: str
    content: str
    should_compress: bool


class SectionSplitter:
    def __init__(self, config: SectioningConfig) -> None:
        self._config = config
        self._file_path_re_real: re.Pattern | None = None
        self._file_path_re_escaped: re.Pattern | None = None

        if config.workspace_path_pattern:
            # File-path heading: ``## <workspace>/<filename>`` lines used by
            # router prompts to mark attached project-context files. The
            # escaped variant must end at whitespace/backslash so the literal
            # ``\\n`` separator stops the match.
            self._file_path_re_real = re.compile(
                rf"\n(## {config.workspace_path_pattern}/\S+)\n"
            )
            self._file_path_re_escaped = re.compile(
                rf"\\n(## {config.workspace_path_pattern}/[^\s\\]+)"
            )

    def split(self, text: str) -> list[SectionInfo]:
        # Newline style: real \n vs escaped \\n (JSON-encoded prompts).
        if "\n" in text and "\\n" not in text[:100]:
            nl = "\n"
            file_path_re = self._file_path_re_real
        elif "\\n" in text:
            nl = "\\n"
            file_path_re = self._file_path_re_escaped
        else:
            nl = "\n"
            file_path_re = self._file_path_re_real

        boundaries: list[tuple[int, str, bool]] = []  # (pos, heading, is_file_path)

        for heading in self._config.primary_headings:
            marker = f"{nl}{heading}{nl}"
            pos = text.find(marker)
            if pos != -1:
                boundaries.append((pos, heading, False))

        if file_path_re:
            for match in file_path_re.finditer(text):
                boundaries.append((match.start(), match.group(1), True))

        boundaries.sort(key=lambda b: b[0])

        if not boundaries:
            return [SectionInfo("entire_text", text, True)]

        sections: list[SectionInfo] = []

        first_pos = boundaries[0][0]
        if first_pos > 0:
            intro = text[:first_pos]
            if intro.strip():
                sections.append(SectionInfo("Intro", intro, False))

        for i, (pos, heading, is_file_path) in enumerate(boundaries):
            end_pos = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            section_text = text[pos:end_pos]

            if is_file_path:
                self._add_file_path_section(sections, heading, section_text, nl)
            else:
                should_compress = heading.strip() not in self._config.preserve_headings
                sections.append(SectionInfo(heading, section_text, should_compress))

        return sections

    def _add_file_path_section(
        self, sections: list[SectionInfo], heading: str, section_text: str, nl: str
    ) -> None:
        # Heading row stays verbatim; content body compresses.
        basename = heading.rsplit("/", 1)[1] if "/" in heading else heading[:40]
        marker = f"{nl}{heading}{nl}"
        marker_len = len(marker)

        sections.append(
            SectionInfo(f"Heading: {basename}", section_text[:marker_len], False)
        )
        remainder = section_text[marker_len:]
        if remainder.strip():
            sections.append(SectionInfo(f"Content: {basename}", remainder, True))
