# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


"""
Prompt templates for video summarization.
"""
from video_analyzer.prompts.prompt_base import BasePrompt
from video_analyzer.schemas.summarization import TASKNAME

# Global summary prompt for the entire video
## Optional: with user input question as customized
## Optional: with user provided subtitles (SubRip format) for the video
GLOBAL_PROMPT = '''
##任务:
请用一个简短流畅的段落概括整段视频，不要提及时间戳。
用户提问: {question}

##字幕:
{chunk_subtitle}

##指南:
- 由于片段描述按时间顺序提供，请保持整体描述连贯，并遵循相同顺序。不要将每个片段的首帧或末帧误认为是整段视频的首帧或末帧。
- 描述语气应像是在直接讲述视频，而不是在总结不同片段的描述。因此避免使用诸如 "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment" 等表述。
- **重要** 需要在视频描述中包含片段描述提供的所有细节。理解视频主题，并提供串联所有片段的连贯叙事。
- **重要** 总结中不要提到时间戳(例如秒或分钟)，让总结听起来像完整的叙事。
- 请结合字幕进行总结，人物对话或旁白可能包含关键信息。

##待总结内容:
以下是视频各子部分的总结。
每个子部分用分隔符 ">|<" 分开。
每个子部分总结会以其相对于完整视频的起止时间开头。
'''

# Macro chunk prompt for summarizing a group of micro chunks
## Optional: with user input question as customized
## Optional: with user provided subtitles (SubRip format) for the video
MACRO_CHUNK_PROMPT = '''
##任务:
请概括整个视频片段，突出所有重要信息，并保留相关时间戳。
用户提问: {question}

##字幕:
{chunk_subtitle}

##指南:
- 片段描述按时间顺序提供，需保持描述连贯并遵循相同顺序。不要把每个片段的首帧或末帧当作整段视频的首帧或末帧。
- 描述语气应像直接讲述视频，而不是总结若干片段，因此避免使用诸如 "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment" 等表述。
- 注意前面片段出现的物体和场景未必出现在当前片段，不要想当然地认为所有片段都有相同元素。
- **重要** 在视频描述中包含片段描述提供的全部细节。理解视频主题，并提供串联所有片段的叙述。
- 摘要中不要包含 "[" 或 "]"。
- 请结合字幕进行总结，人物对话或旁白可能包含关键信息。

##待总结内容:
以下是视频片段各子部分的总结。
开始时间: {st_tm} 秒
结束时间: {end_tm} 秒
每个子部分用分隔符 ">|<" 分开。
每个子部分总结会以其相对于完整视频的起止时间开头。
- 输出中不要重复 "开始时间" 和 "结束时间"。
'''

# Local prompt for summarizing a single micro chunk
## Optional: with user input question as customized
## Optional: with user provided subtitles (SubRip format) for the video
LOCAL_PROMPT = '''
##任务:
请概括该视频片段。
开始时间: {st_tm} 秒
结束时间: {end_tm} 秒
用户提问: {question}

##字幕:
{chunk_subtitle}

##指南:
- 分析画面序列所暗示的叙事发展，整体理解该序列。
- 这些画面取自同一片段，相邻帧可能差别很小，不要误判为特效。
- 如果画面出现文字，请以原语言描述，并在括号中给出英文翻译，例如: 书本 (book)。同时说明该文字在场景中的含义。
- 提及人物时，用服饰等特征区分不同人物。
- **重要** 尽可能提供详细描述，涵盖物体的颜色、形状、质感，人物的动作与特征，以及场景与背景。
- 摘要中不要包含 "[" 或 "]"。
- 输出中不要包含 "开始时间" 和 "结束时间"。
- 请结合字幕进行总结，人物对话或旁白可能包含关键信息。
'''

# Previous context prompt for providing context from previous chunk
T_MINUS_1_PROMPT = '''
##上下文:
前 {dur} 秒的视频总结放在方括号 [] 中。
**重要** 需要将上一片段的描述视为上下文，并总结接下来的视频片段。
**重要** 不要在输出中复制上一片段的总结。
[
开始时间: {st_tm} 秒
结束时间: {end_tm} 秒
{past_summary}
]
'''


class SummaryZhPrompt(BasePrompt):
	TASK_NAME: str = TASKNAME.SUMMARY_ZH.value
	DESCRIPTION: str = "General-purpose video summarization for arbitrary scenes (Chinese prompts)."

	@staticmethod
	def _remove_user_prompt_line(lines):
		return [ln for ln in lines if not ln.strip().startswith('User prompt:')]

	@staticmethod
	def _remove_subtitles_section(lines):
		out = []
		skip = 0
		for i, ln in enumerate(lines):
			if skip:
				skip -= 1
				continue
			if ln.strip().startswith('##Subtitles:'):
				skip = 1
				if i + 2 < len(lines) and not lines[i + 2].strip():
					skip = 2
				continue
			out.append(ln)
		while out and not out[0].strip():
			out.pop(0)
		while out and not out[-1].strip():
			out.pop()
		return out

	def assign_global_prompt(self, **kwargs) -> str:
		template = GLOBAL_PROMPT
		# Allow both 'chunk_subtitle' and 'subtitles' as input keys
		q = kwargs.get('question', '')
		subs = kwargs.get('chunk_subtitle', '')
		rendered = self._render_validated(
			template,
			kwargs,
			optional_fields={"question", "chunk_subtitle"},
		)
		lines = rendered.splitlines()
		if not str(q).strip():
			lines = self._remove_user_prompt_line(lines)
		if not str(subs).strip():
			lines = self._remove_subtitles_section(lines)
		return "\n".join(lines) + "\n"

	def assign_macro_prompt(self, **kwargs) -> str:
		template = MACRO_CHUNK_PROMPT
		q = kwargs.get('question', '')
		subs = kwargs.get('chunk_subtitle', '')
		rendered = self._render_validated(
			template,
			kwargs,
			optional_fields={"question", "chunk_subtitle"},
		)
		lines = rendered.splitlines()
		if not str(q).strip():
			lines = self._remove_user_prompt_line(lines)
		if not str(subs).strip():
			lines = self._remove_subtitles_section(lines)
		return "\n".join(lines) + "\n"

	def assign_local_prompt(self, **kwargs) -> str:
		template = LOCAL_PROMPT
		q = kwargs.get('question', '')
		subs = kwargs.get('chunk_subtitle', '')
		rendered = self._render_validated(
			template,
			kwargs,
			optional_fields={"question", "chunk_subtitle"},
		)
		lines = rendered.splitlines()
		if not str(q).strip():
			lines = self._remove_user_prompt_line(lines)
		if not str(subs).strip():
			lines = self._remove_subtitles_section(lines)
		return "\n".join(lines) + "\n"

	def assign_t_minus_prompt(self, **kwargs) -> str:
		return self._render_validated(
			T_MINUS_1_PROMPT,
			kwargs,
			optional_fields=set(),
		)


if __name__ == "__main__":
	from video_analyzer.utils.summarization_utils import redact_base64

	# Demo: call SummaryZhPrompt methods directly (no prompt_builder)
	sp = SummaryZhPrompt()

	# Global prompt examples
	global_kwargs_with_all = {
		"question": "Summarize key events in the video.",
		"chunk_subtitle": "1\n00:00:00,000 --> 00:00:03,000\nHello world\n",
	}
	global_kwargs_minimal = {}

	# Macro prompt examples (requires st_tm and end_tm)
	macro_kwargs = {
		"question": "Highlight important events with timestamps.",
		"chunk_subtitle": "2\n00:00:03,000 --> 00:00:06,000\nAnother line\n",
		"st_tm": 0,
		"end_tm": 12,
	}
	macro_kwargs_no_q_sub = {"st_tm": 0, "end_tm": 12}

	# Local prompt examples (requires st_tm and end_tm)
	local_kwargs = {
		"question": "Describe this segment.",
		"chunk_subtitle": "3\n00:00:06,000 --> 00:00:09,000\nSegment text\n",
		"st_tm": 6,
		"end_tm": 9,
	}
	local_kwargs_minimal = {"st_tm": 6, "end_tm": 9}

	# T-minus prompt example (context from previous segment)
	tminus_kwargs = {
		"dur": 10,
		"st_tm": 12,
		"end_tm": 22,
		"past_summary": "Previous segment describes an introduction and setup.",
	}

	print("=== GLOBAL (with question & subtitles) ===\n")
	print(redact_base64(sp.assign_global_prompt(**global_kwargs_with_all)))

	print("\n=== GLOBAL (no question/subtitles) ===\n")
	print(redact_base64(sp.assign_global_prompt(**global_kwargs_minimal)))

	print("\n=== MACRO (with question & subtitles) ===\n")
	print(redact_base64(sp.assign_macro_prompt(**macro_kwargs)))

	print("\n=== MACRO (no question/subtitles) ===\n")
	print(redact_base64(sp.assign_macro_prompt(**macro_kwargs_no_q_sub)))
	print("\n=== LOCAL (with question & subtitles) ===\n")
	print(redact_base64(sp.assign_local_prompt(**local_kwargs)))

	print("\n=== LOCAL (no question/subtitles) ===\n")
	print(redact_base64(sp.assign_local_prompt(**local_kwargs_minimal)))

	print("\n=== T-MINUS (context prompt) ===\n")
	print(redact_base64(sp.assign_t_minus_prompt(**tminus_kwargs)))
