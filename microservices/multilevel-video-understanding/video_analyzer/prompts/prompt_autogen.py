# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Autogen mode: ask the service's own LLM to draft a four-section prompt set.

Kept intentionally thin — users are expected to prefer the `full` mode where
the OpenClaw harness's stronger provider drafts the prompt and posts it here
for registration. Autogen is a lightweight fallback for quick experiments.
"""

from __future__ import annotations

import re
from typing import Dict

from video_analyzer.prompts.prompt_registry import (
    ANCHOR_NAMES, ANCHOR_TO_KEY, REFERENCE_TEMPLATE, RegistryError, parse_full_content,
)
from video_analyzer.model_serving.openai_llm import LLM


META_PROMPT_TEMPLATE = """\
你是一个专门为视频摘要服务撰写 prompt 的助手。请根据下面的场景描述,
生成 4 段用于多层级视频理解的 prompt,并以 **Python 模块常量** 的格式输出。

场景描述:
{description}

严格要求:
1. **必须**包含且只包含以下 4 个顶层赋值(大小写必须与示例一致):
   - GLOBAL_PROMPT     — 整段视频的总结,可用 {{question}} 引用用户问题(可选占位符)
   - MACRO_CHUNK_PROMPT — 时间段(分钟级)摘要,必须包含占位符 {{st_tm}} 和 {{end_tm}}
   - LOCAL_PROMPT      — 单个片段(秒级)的详细描述,必须包含占位符 {{st_tm}} 和 {{end_tm}}
   - T_MINUS_1_PROMPT  — 前一片段上下文,必须包含 {{dur}}, {{st_tm}}, {{end_tm}}, {{past_summary}}

2. 每段赋值的字符串字面量必须用三单引号 `'''...'''` 包裹,可跨多行。
3. 段与段之间可以留空行或写注释,但**不要**有其他任何顶层赋值。
4. 语言:根据场景描述自动选择中文或英文,段内保持一致。
5. 整体风格参照智能家居监控 prompt:`##任务:` + 指南 + 占位符。
6. **不要**在任何段中使用 Markdown 代码块(```)或字符串 "<<<",否则会被拒绝。

输出示例(仅展示结构,不要复用其中内容):

GLOBAL_PROMPT = '''
...
'''

MACRO_CHUNK_PROMPT = '''
...
'''

LOCAL_PROMPT = '''
...
'''

T_MINUS_1_PROMPT = '''
...
'''

请直接输出上述 4 个赋值块,不要添加任何前言、标题或结语。
"""


def _build_meta_prompt(description: str) -> str:
    return META_PROMPT_TEMPLATE.format(description=description.strip())


def _strip_markdown_fences(text: str) -> str:
    """If the LLM wrapped the answer in a ```python ... ``` fence, unwrap it."""
    # Common fence variations.
    stripped = text.strip()
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```$", stripped, re.DOTALL)
    if m:
        return m.group(1)
    return stripped


async def generate_prompt_set(description: str, llm: LLM) -> Dict[str, str]:
    """Invoke the LLM once and parse its output into the four sections.

    Returns a dict with keys global / macro / local / t_minus (unfilled —
    the registry applies smart auto-fill afterwards).
    Raises RegistryError on empty / unparsable output.
    """
    if not description or not description.strip():
        raise RegistryError(
            400, "empty_description",
            detail="autogen requires a non-empty description",
        )

    meta = _build_meta_prompt(description)
    raw = await llm.async_infer(meta)
    if not raw or not raw.strip():
        raise RegistryError(
            422, "autogen_empty_output",
            detail="LLM returned empty content",
            reference_template=REFERENCE_TEMPLATE,
        )

    cleaned = _strip_markdown_fences(raw)
    try:
        sections = parse_full_content(cleaned)
    except RegistryError as e:
        # Enrich the error with the raw LLM output so clients can inspect.
        e.detail["llm_raw_output"] = raw[:4000]
        raise
    return sections
