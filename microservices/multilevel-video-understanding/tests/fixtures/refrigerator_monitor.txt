"""Consolidated fridge dynamic-task content (English), used as a test fixture.

This is the merged refrigerator task the service ships as an *example* of a
dynamic task — it is NOT a built-in. Registering it exercises the /v1/tasks
`full` mode and the caption-only summary path.

Two execution modes share this single task name (mirroring child_safety /
elder_wakeup):

  1. **Realtime narrative summarization** (per motion clip → /v1/summary):
     only LOCAL_PROMPT runs (single chunk per clip), producing a free-form
     English narrative of door state / items / person actions.
  2. **Daily-report aggregation** (caption-only /v1/summary over the day's SRT):
     LOCAL is skipped; MACRO_CHUNK_PROMPT + GLOBAL_PROMPT consume the SRT and
     emit a structured report (activity / inventory / suggestions / habits /
     dietary advice).

Placeholders (auto-filled by the video-summary service):
  {question}      — optional user prompt
  {st_tm}         — chunk start time in seconds
  {end_tm}        — chunk end time in seconds
  {dur}           — previous chunk duration (T_MINUS_1)
  {past_summary}  — previous chunk summary (T_MINUS_1)
"""

GLOBAL_PROMPT = '''
##Task:
Summarize the following refrigerator events into a brief report.
**Important: The timestamps (HH:MM:SS) are real Beijing time in 24-hour format, NOT video playback time. Examples: 06:30 = 6:30 AM, 12:15 = 12:15 PM, 17:03 = 5:03 PM, 22:00 = 10:00 PM. Use these to accurately determine activity periods**
**Event types: Each SRT entry is prefixed with [motion] or [static]. [motion] = fridge door was opened — count these as door openings. [static] = idle period, no usage — do NOT count as door openings.**
User prompt: {question}

##Please strictly follow the template below (replace content in angle brackets; remove entire sections if no content applies):

Today's Refrigerator Activity Summary: <Two or three sentences summarizing main activities, including types of items involved and usage time patterns>

Current Inventory (estimated from today's activity):
- <Item A>: <quantity remaining> — <status: well-stocked / running low / used up>
- <Item B>: <quantity remaining> — <status>

Suggestions: <One sentence of advice>

User Habit Analysis: <One sentence describing peak times and frequency>

Dietary Advice: <One sentence of health advice>

##Example Output:

Today's Refrigerator Activity Summary: Mainly milk and yogurt were taken out, concentrated in the morning and evening periods, with higher frequency in the evening.

Inventory Alerts:
- Milk has only 1 carton remaining, suggest restocking
- Yogurt has been used up

User Habit Analysis: Door openings are concentrated between 7-8 AM and 6-7 PM; mornings are mainly for breakfast items.

##Rules:
- Do not list the time and details of each individual door opening
- Each section should be at most one sentence
- If there are no events, output only "No door opening events detected"

##Content to Summarize:
The following events are separated by ">|<".
'''


MACRO_CHUNK_PROMPT = '''
##Task:
Summarize the refrigerator usage during this period in 2-3 sentences.
**Note: The timestamps in the events represent real wall-clock time (Beijing time) (e.g., 17:03 = 5:03 PM).**
**Event types: Each SRT entry is prefixed with [motion] or [static]. [motion] = fridge door was opened — count these as door openings. [static] = idle period, no usage — do NOT count as door openings.**
Start time: {st_tm} seconds
End time: {end_tm} seconds
User prompt: {question}

##Output Format (strictly 2-3 sentences):
Sentence 1: Items involved: <item name + quantity + taken out/put in>.
Sentence 2: <Change in remaining quantity>.
Sentence 3 (if applicable): <Abnormal behavior>.

##Example Output:
Items involved: 2 cartons of milk taken out, 1 bottle of soda put in. Milk has 1 carton remaining.

##Rules:
- Merge duplicate items, only write aggregated quantities
- Do not list each individual door opening
- Do not output "[" or "]"

##Content to Summarize:
The following sub-events are separated by ">|<".
'''


LOCAL_PROMPT = '''
##Task:
You are analyzing a video clip from a smart home refrigerator monitoring camera. Please describe in detail all refrigerator-related activities in this clip.
Start time: {st_tm} seconds
End time: {end_tm} seconds
User prompt: {question}

##Guidelines:
- Focus on the following:
  1. Refrigerator door status: Whether the door is open, closed, or half-open; changes in door opening angle.
  2. Item interactions: Describe in detail each item taken out of or put into the refrigerator, including item type (food, beverage, container, etc.), color, shape, and packaging characteristics.
  3. Refrigerator interior: If the interior is visible, describe the visible arrangement of items.
  4. Person actions: Describe the specific actions of people in front of the refrigerator (bending, reaching, rummaging, standing and waiting, etc.).
- **Important** Keep the output concise while covering the key points above; this information will be used for subsequent event analysis and anomaly detection.
- If text appears in the frame (e.g., food labels), describe it in the original language and provide a translation in parentheses.
- If there is no refrigerator-related activity in this clip (e.g., a person merely walks past), describe the scene content as-is.
- Do not include "[" or "]" in the summary.
- Do not include "Start time" or "End time" in the output.
'''


T_MINUS_1_PROMPT = '''
##Previous Summary (do not copy, use as reference only):
Start time: {st_tm} seconds
End time: {end_tm} seconds
Previous summary (last {dur} seconds): {past_summary}

Note: pay attention to the refrigerator door status and people from the previous clip; maintain continuity in the current clip description. Do not copy the previous summary into the output.
'''
