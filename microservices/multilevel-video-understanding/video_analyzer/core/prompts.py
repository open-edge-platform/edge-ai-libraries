# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


"""
Prompt templates for video summarization.
"""

# Global summary prompt for the entire video
GLOBAL_PROMPT = '''
##Task:
Please create a summary of the overall video in short and fluent format within a single paragraph, do not mention timestamp.

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- **IMPORTANT** Do not mention timestamp (for example second or minute) in the summary, therefore the summary looks like a whole narrative.

##Inputs to be summarized:
The following are summaries of subsections of a video.
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
'''

# Global summary prompt for the entire video, with user input question as customized
GLOBAL_PROMPT_WITH_QUESTION = '''
##Task:
Please create a summary of the overall video in short and fluent format within a single paragraph, do not mention timestamp.
User prompt: {question}

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- **IMPORTANT** Do not mention timestamp (for example second or minute) in the summary, therefore the summary looks like a whole narrative.

##Inputs to be summarized:
The following are summaries of subsections of a video.
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
'''

# Macro chunk prompt for summarizing a group of micro chunks
MACRO_CHUNK_PROMPT = '''
##Task:
Please create a summary of the overall video, highlighting all important information, including timestamps.

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- Note that some objects and scenes shown in the previous segments might not shown in the current segment. Be carefully do not assume the same object and scenes shown in every segments.
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- Do not contain any "[" or "]" in the summary.

##Inputs to be summarized:
The following are summaries of subsections of a video segment.
Start time: {st_tm} sec
End time: {end_tm} sec
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
- Do not repeat "Start time" and "End time" in the output
'''

# Macro chunk prompt for summarizing a group of micro chunks, with user input question as customized
MACRO_CHUNK_PROMPT_WITH_QUESTION = '''
##Task:
Please create a summary of the overall video, highlighting all important information, including timestamps.
User prompt: {question}

##Guideline:
- Since the segment descriptions are provided in chronological order, ensure that the video description is coherent and follows the same sequence. Avoid referring to the first or final frame of each segment as the first or final frame of the entire video.
- The tone of the video description should be as if you are describing a video directly instead of summarizing the information from several segment descriptions. Therefore, avoid phrases found in the referred segment descriptions such as "The segment begins...", "As the segment progresses...", "The segment concludes", "The final/first frame", "The second segment begins with", "The final frames of this segment", etc
- Note that some objects and scenes shown in the previous segments might not shown in the current segment. Be carefully do not assume the same object and scenes shown in every segments.
- **IMPORTANT** Include all details from the given segment descriptions in the video description. Try to understand of the theme of the video and provide a coherent narrative that connects all the segments together.
- Do not contain any "[" or "]" in the summary.

##Inputs to be summarized:
The following are summaries of subsections of a video segment.
Start time: {st_tm} sec
End time: {end_tm} sec
Each subsection summary is separated by the delimiter ">|<".
Each subsection summary will start with the start and end timestamps of the subsection relative to the full video.
- Do not repeat "Start time" and "End time" in the output
'''

# Local prompt for summarizing a single micro chunk
LOCAL_PROMPT = '''
##Task:
Please summarize the video segment
Start time: {st_tm} sec
End time: {end_tm} sec

##Guideline:
- Analyze the narrative progression implied by the sequence of frames, interpreting the sequence as a whole.
- Note that since these frames are extracted from a segment, adjacent frames may show minimal differences. These should not be interpreted as special effects in the segment.
- If text appears in the frames, you must describe the text in its original language and provide an English translation in parentheses. For example: 书本 (book). Additionally, explain the meaning of the text within its context.
- When referring to people, use their characteristics, such as clothing, to distinguish different people.
- **IMPORTANT** Please provide as many details as possible in your description, including colors, shapes, and textures of objects, actions and characteristics of humans, as well as scenes and backgrounds.
- Do not contain any "[" or "]" in the summary.
- Do not include "Start time" and "End time" in the output
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
