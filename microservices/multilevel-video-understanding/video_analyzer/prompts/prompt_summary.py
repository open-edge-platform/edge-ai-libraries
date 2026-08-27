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
##Task:
Please create a summary of the overall video in short and fluent format within a single paragraph, do not mention timestamp.
User prompt: {question}

##Subtitles:
{chunk_subtitle}

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- **IMPORTANT** Do not mention timestamp (for example second or minute) in the summary, therefore the summary looks like a whole narrative.
- Please summarize with the help of subtitles, the dialogue between characters or narration may provide key information.

##Inputs to be summarized:
The following are summaries of subsections of a video.
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
'''

# Macro chunk prompt for summarizing a group of micro chunks
## Optional: with user input question as customized
## Optional: with user provided subtitles (SubRip format) for the video
MACRO_CHUNK_PROMPT = '''
##Task:
Please create a summary of the overall video, highlighting all important information, including timestamps.
User prompt: {question}

##Subtitles:
{chunk_subtitle}

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- Note that some objects and scenes shown in the previous segments might not shown in the current segment. Be carefully do not assume the same object and scenes shown in every segments.
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- Do not contain any "[" or "]" in the summary.
- Please summarize with the help of subtitles, the dialogue between characters or narration may provide key information.

##Inputs to be summarized:
The following are summaries of subsections of a video segment.
Start time: {st_tm} sec
End time: {end_tm} sec
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
- Do not repeat "Start time" and "End time" in the output
'''

# Local prompt for summarizing a single micro chunk
## Optional: with user input question as customized
## Optional: with user provided subtitles (SubRip format) for the video
LOCAL_PROMPT = '''
##Task:
Please summarize the video segment
Start time: {st_tm} sec
End time: {end_tm} sec
User prompt: {question}

##Subtitles:
{chunk_subtitle}

##Guideline:
- Analyze the narrative progression implied by the sequence of frames, interpreting the sequence as a whole.
- Note that since these frames are extracted from a segment, adjacent frames may show minimal differences. These should not be interpreted as special effects in the segment.
- If text appears in the frames, you must describe the text in its original language and provide an English translation in parentheses. For example: 书本 (book). Additionally, explain the meaning of the text within its context.
- When referring to people, use their characteristics, such as clothing, to distinguish different people.
- **IMPORTANT** Please provide as many details as possible in your description, including colors, shapes, and textures of objects, actions and characteristics of humans, as well as scenes and backgrounds.
- Do not contain any "[" or "]" in the summary.
- Do not include "Start time" and "End time" in the output
- Please summarize with the help of subtitles, the dialogue between characters or narration may provide key information.
'''

# Previous context prompt for providing context from previous chunk
T_MINUS_1_PROMPT = '''
##Context:
Summary of the past {dur} seconds video segment is in brackets []
**IMPORTANT** Your description should see the description of previous segment as context and summarize the next video segment
**IMPORTANT** Do not copy the summary of the previous segment in your output
[
Start time: {st_tm} sec
End time: {end_tm} sec
{past_summary}
]
'''


class SummaryPrompt(BasePrompt):
	TASK_NAME: str = TASKNAME.SUMMARY.value
	DESCRIPTION: str = "General-purpose video summarization for arbitrary scenes — default task when no domain-specific prompt applies."
 
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
	import tiktoken
	from video_analyzer.utils.summarization_utils import redact_base64

	def num_tokens_from_string(string: str, encoding_name: str) -> int:
		"""Returns the number of tokens in a text string."""
		encoding = tiktoken.get_encoding(encoding_name)
		num_tokens = len(encoding.encode(string))
		return num_tokens

	# Demo: call SummaryPrompt methods directly (no prompt_builder)
	sp = SummaryPrompt()

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

	# print("=== GLOBAL (with question & subtitles) ===\n")
	# global_prompt = sp.assign_global_prompt(**global_kwargs_with_all)
	# # print(redact_base64(global_prompt))
	# num_tokens = num_tokens_from_string(global_prompt, "cl100k_base")
	# print(f"Number of tokens: {num_tokens}")

	print("\n=== GLOBAL (no question/subtitles) ===\n")
	global_prompt_minimal = sp.assign_global_prompt(**global_kwargs_minimal)
	# print(redact_base64(global_prompt_minimal))
	num_tokens = num_tokens_from_string(global_prompt_minimal, "cl100k_base")
	print(f"Number of tokens: {num_tokens}")

	# print("\n=== MACRO (with question & subtitles) ===\n")
	# macro_prompt = sp.assign_macro_prompt(**macro_kwargs)
	# # print(redact_base64(macro_prompt))
	# num_tokens = num_tokens_from_string(macro_prompt, "cl100k_base")
	# print(f"Number of tokens: {num_tokens}")

	print("\n=== MACRO (no question/subtitles) ===\n")
	macro_prompt_no_q_sub = sp.assign_macro_prompt(**macro_kwargs_no_q_sub)
	# print(redact_base64(macro_prompt_no_q_sub))
	num_tokens = num_tokens_from_string(macro_prompt_no_q_sub, "cl100k_base")
	print(f"Number of tokens: {num_tokens}")
	
	# print("\n=== LOCAL (with question & subtitles) ===\n")
	# local_prompt = sp.assign_local_prompt(**local_kwargs)
	# # print(redact_base64(local_prompt))
	# num_tokens = num_tokens_from_string(local_prompt, "cl100k_base")
	# print(f"Number of tokens: {num_tokens}")

	print("\n=== LOCAL (no question/subtitles) ===\n")
	local_prompt_minimal = sp.assign_local_prompt(**local_kwargs_minimal)
	# print(redact_base64(local_prompt_minimal))
	num_tokens = num_tokens_from_string(local_prompt_minimal, "cl100k_base")
	print(f"Number of tokens: {num_tokens}")

	print("\n=== T-MINUS (context prompt) ===\n")
	tminus_prompt = sp.assign_t_minus_prompt(**tminus_kwargs)
	# print(redact_base64(tminus_prompt))
	num_tokens = num_tokens_from_string(tminus_prompt, "cl100k_base")
	print(f"Number of tokens: {num_tokens}")