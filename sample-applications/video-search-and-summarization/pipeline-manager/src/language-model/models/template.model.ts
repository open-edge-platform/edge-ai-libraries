// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// export const CaptionsSummarizeTemplate = `
// You will be given captions from sequential clips of a video. Group the captions based on whether they are related to one another or create a continuous scene:

// %data%
// `;

// export const CaptionsSummarizeTemplate = `
// You will be given captions generated from individual frames of a video clip. Group the captions based on whether they are related to one another or create a continuous scene. Ensure the summary captures the main activities, objects, people and events in a logical and chronological order:

// %data%
// `;

// export const CaptionsSummarizeTemplate = `
// You will be given a series of captions from individual frames of a video clip, containing brief description of each frame. Your task is to weave these captions into a coherent narrative that highlights the detail about objects or people or events seen in the clip in a logical and chronological order. Avoid describing the scenery, and rather focus on activities or events happening in the clip. Avoid speculation or unnecessary attribution of details :

// %data%
// `;

export const CaptionsSummarizeTemplate = `
You will be given a series of captions from individual frames of a video clip, containing brief description of each frame. Your task is to weave these captions into summary for that clip, that not only groups related scenes, but also highlights the main activities and details about objects or people or events seen in the clip in a logical and chronological order. While referring to an object or person, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details :

%data%
`;

// export const CaptionsSummarizeTemplate = `
// You will be given a series of captions from individual frames of a video clip, containing brief description of each frame. Your task is to weave these captions into a concise coherent narrative that not only groups related scenes, but also highlights the main activities and details about objects or people or events seen in the clip in a logical and chronological order. While referring to an object or person, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details :

// %data%
// `;

// export const CaptionsReduceTemplate = `
// You will be given summaries of captions from sequential clips of a video. Create a concise summary of these summaries:

// %data%
// `;
export const CaptionsReduceTemplate = `
You will be given summaries of image descriptions for a video clip, which were batched and summarized in previous steps. Your task is to create a single final summary that maintains the chronological order of events or activity in the scenes and does not miss out on any details. Ensure that the summary is coherent and captures all the important activities, objects, people, and events:

%data%
`;

export const CaptionsReduceSingleTextTemplate = `
Reduce the following image description. Ensure that the summary retains the key details and main activities, but is concise and to the point. If objects or people are identified, try to retain that information in the summary:

%data%
`;

export const ChunkSummarizeTemplate = `
You will be given summaries of video chunks from a video clip, which were previously batched and summarized. Your task is to create a final summary that describes the activities and events captured. The generated summary should be organized chronologically and logically. It should be concise yet descriptive, covering all important events. Format the output in markdown for clarity:

%data%
`;

export const ChunkReduceTemplate = `
You will be given summaries of video chunks for a video clip, which were batched and summarized in previous steps. Your task is to create a concise summary that describes the activities and events captured. Ensure that the summary maintains the chronological order of events or activities in the scenes and does not miss out on any details. The summary should be coherent and capture all the important activities, objects, people, and events. This should be a concise, yet descriptive summary of all the important events.: 

%data%
`;

export const ChunkReduceSingleTextTemplate = `
Reduce the following video chunk summary. Ensure that the summary retains the key details and main activities, but is concise and to the point. If objects or people are identified, try to retain that information in the summary: 

%data%
`;

export const FrameCaptionTemplateWithObjects = `
The following is seen in the image: 

%data%. 

Describe the activities and events captured in the image. Provide a detailed description of what is happening. While referring to an object or person or entity, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details.
`;

export const FrameCaptionTemplateWithoutObjects = `
Describe the activities and events captured in the image. Provide a detailed description of what is happening. While referring to an object or person or entity, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details.
`;

export const MultipleFrameCaptionTemplateWithoutObjects = `
Describe the activities and events captured in the images. Provide a detailed description of what is happening. While referring to an object or person or entity, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details.
`;

export const PromptTemplates = {
  defaultFrames: `The images are sequential frames from a video. Analyze them to provide a concise description (2–3 sentences) of the scene, including:
- Key activities, events, and interactions
- Notable objects, people, and environment details
- Any changes or motion observed across frames
Focus on what is visually evident. Do not speculate beyond what the frames show.`,
  defaultSummary: `  
You are provided with chunk-by-chunk summaries of a single video. Generate one cohesive summary of the entire video. Ensure that the summary:
- Describes key actions, interactions, and notable details in chronological order.
- Highlights important objects, people, and contextual information.
- Avoids unnecessary repetition and maintains coherence.
- Does not reference internal chunk numbers, frame indices, or segment boundaries.
Format the output in Markdown.
%audio_summary%
Video Segment Summaries:

%data%
`,
  defaultReduce: `
You are provided with multiple intermediate summaries of video segments from previous summarization passes. Combine them into a single, cohesive narrative. The merged summary should:

- Maintain chronological order and logical flow of events across all segments.
- Preserve key activities, interactions, people, objects, and notable details.
- Use consistent identifiers for recurring people or objects across segments (e.g., "Person A", "the red vehicle", "Officer 1").
- Merge overlapping or redundant descriptions rather than repeating them.
- Do not introduce information not present in the provided summaries.

Intermediate Summaries:

%data%
  `,
  defaultSingle: `
Condense the following video summary into a shorter version while preserving essential information:

- Retain key events, actions, and interactions in chronological order.
- Preserve identifiers for people, objects, or entities mentioned.
- Prioritize factual detail over verbose description.
- Do not add information not present in the original summary.

%data%
  `,

  // bodyCamFrames: `The Images are from a Law enforcement body cam point of view. Describe the activities and events captured by the body camera. Provide a detailed description of what is happening.`,

  bodyCamFrames: `
The images are sequential frames captured from a law enforcement body camera, offering a first-person perspective. Analyze the sequence of frames to provide a detailed description of the activities, events, and interactions observed. Ensure the description:

- Captures the temporal progression and continuity across frames.
- Highlights key actions, interactions, and notable objects or details.
- Provides relevant context to explain the observed events.
- Avoid referencing internal frames as checkpoint when creating the sequence of events.

Focus on creating a coherent narrative that reflects the sequence of events accurately.
`,

  // bodyCamFrames: `The images are sequential frames captured from a law enforcement body camera, providing a first-person perspective. Analyze the sequence of frames to describe the activities, events, and interactions observed. Provide a detailed and coherent description that captures the progression of events, key actions, notable objects, and any relevant context across the frames. Ensure the description reflects temporal continuity and highlights significant details.`,

  // bodyCamSummary: `Analyze the provided summaries of video segments captured from a law enforcement body camera. Based on the available information, generate a summary that describes the activities and events captured. The summary should be organized chronologically and in logical sections. This should be a concise, yet descriptive summary of all the important events. Format the output in markdown for clear display:`,
  //   bodyCamSummary: `
  // Analyze the provided summaries of video segments captured from a law enforcement body camera. Your task is to generate a comprehensive and concise narrative of the events and activities observed in the video. Ensure the narrative is descriptive, highlights key actions, interactions, and notable details, events or information, and avoids unnecessary repetition. Format the output in clear and structured Markdown, using bullet points or headings if necessary to improve readability.

  // %data%
  // `,

  bodyCamSummary: `
You are provided with summaries of video segments of single video captured from a law enforcement body camera. Your task is to generate a single detailed yet focused summary (aim for 2–4 paragraphs) of the entire video. Ensure that the summary:
- Clearly describes key actions, interactions, and notable details.
- Highlights important objects, people, and contextual information.
- Avoids unnecessary repetition and maintains coherence.
Don't treat internal video segments as checkpoints as those are just random segments and avoid referencing internal frames or segments, but rather create chronological or logical order of events. Format the output in Markdown.
%audio_summary%
Video Segments:

%data%
`,

  //   bodyCamReduce: `
  // You will be given summaries of video chunks from a video clip of a Law enforcement body camera point of view. Your task is to create a summary that describes the activities and events captured. The generated summary should be concise yet descriptive, covering all important events. The summary should be coherent and capture all the important activities, objects, people, and events.:

  // %data%
  // `,
  //   bodyCamReduce: `
  // You will be provided with multiple summaries of video segments captured from a law enforcement body camera. Your task is to synthesize these summaries into a single, cohesive narrative that accurately describes the key activities, events, interactions, and notable details observed across the entire video. Ensure the combined narrative reflects temporal continuity and highlights significant details while avoiding redundancy. Focus on capturing the most important information from the provided summaries.

  // %data%
  // `,

  bodyCamReduce: `
You are provided with multiple intermediate summaries of video segments from a law enforcement body camera. Combine them into a single, cohesive and chronologically accurate narrative. The merged summary should:

- Maintain chronological order and logical flow of events across all segments.
- Preserve key actions, commands, interactions, people, and notable details.
- Use consistent identifiers for recurring individuals or objects across segments (e.g., "Person A", "the red vehicle", "Officer 1").
- Merge overlapping or redundant descriptions rather than repeating them.
- Do not introduce information not present in the provided summaries.

Intermediate Summaries:

%data%
`,

  //   bodyCamSingle: `
  // Reduce the following video summary. Ensure that the summary retains the key details and main activities, but is concise and to the point. If objects or people are identified, try to retain that information in the summary:

  // %data%
  // `,
  bodyCamSingle: `
Condense the following body-cam video summary into a shorter version while preserving essential information:

- Retain key events, actions, commands, and interactions in chronological order.
- Preserve identifiers for people, objects, or entities mentioned.
- Prioritize factual and operationally relevant detail over verbose description.
- Do not add information not present in the original summary.

%data%
`,

  defaultAudioSummary: `
You are provided with a full transcript of a video's spoken audio. Create a coherent, chronologically ordered summary focused on speech content, key topics, decisions, intent, and relevant context.

Requirements:
- Preserve important details and sequence of ideas.
- Remove filler speech and repeated wording.
- Avoid speculation and information not present in transcript.
- Keep speaker references neutral if speaker identity is unclear.

Full Transcript:

%data%
`,

  defaultAudioReduce: `
You are provided with intermediate summaries derived from a full audio transcript. Merge them into one coherent final summary (aim for 2–4 paragraphs) while preserving chronology, key points, and critical details.

%data%
`,

  defaultAudioSingle: `
Condense the following audio-transcript summary while retaining the key points, chronology, and critical details:

%data%
`,

  bodyCamAudioSummary: `
You are provided with a full transcript of spoken audio from a law-enforcement body camera recording. Create a coherent, chronological summary of speech content, including commands, responses, notable statements, situational cues, and critical events.

Requirements:
- Preserve factual sequence and important details.
- Keep wording neutral and avoid speculation.
- Exclude filler or repeated speech unless operationally important.

Full Transcript:

%data%
`,

  bodyCamAudioReduce: `
You are provided with intermediate summaries of body-cam audio transcript content. Merge them into one chronologically accurate final summary (aim for 2–4 paragraphs), preserving key commands, responses, and critical statements.

%data%
`,

  bodyCamAudioSingle: `
Condense the following body-cam audio transcript summary while preserving chronology and critical speech details:

%data%
`,
};
