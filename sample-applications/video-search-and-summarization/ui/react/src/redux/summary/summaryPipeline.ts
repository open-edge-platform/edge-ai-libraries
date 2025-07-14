import { Video } from '../video/video';
import { EVAMPipelines } from './summary';

export interface SummaryPipelineSampling {
  videoStart?: number;
  videoEnd?: number;
  chunkDuration: number;
  samplingFrame: number;
  frameOverlap: number;
  multiFrame: number;
}

export interface SummaryPipelinePrompts {
  framePrompt?: string;
  summaryMapPrompt?: string;
  summaryReducePrompt?: string;
  summarySinglePrompt?: string;
}

export interface SummaryPipelineAudio {
  audioModel: string;
}

export interface SummaryPipelineEvam {
  evamPipeline: EVAMPipelines;
}

export interface SummaryPipelineDTO {
  videoId: string;
  video?: Video;
  title: string;
  sampling: SummaryPipelineSampling;
  evam: SummaryPipelineEvam;
  prompts?: SummaryPipelinePrompts;
  audio?: SummaryPipelineAudio;
}

export interface SummaryPipelinRO {
  summaryPipelineId: string;
}
