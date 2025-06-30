// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Injectable } from '@nestjs/common';
import {
  CaptionsSummarizeTemplate,
  CaptionsReduceTemplate,
  CaptionsReduceSingleTextTemplate,
  ChunkSummarizeTemplate,
  ChunkReduceTemplate,
  ChunkReduceSingleTextTemplate,
  FrameCaptionTemplateWithObjects,
  FrameCaptionTemplateWithoutObjects,
  MultipleFrameCaptionTemplateWithoutObjects,
  PromptTemplates,
} from '../models/template.model';
// import { join } from 'path';

@Injectable()
export class TemplateService {
  getVideoTemplate() {}

  getTemplate(name: string): string {
    return PromptTemplates[name] ?? '';
  }

  getTemplateWithReplacements(
    name: string,
    subs: Record<string, string>,
  ): string | undefined {
    let template: string = this.getTemplate(name);

    for (const key in subs) {
      template = template.replaceAll(`%${key}%`, subs[key]);
    }

    return template;
  }

  addDetectedObjects(prompt:string, detectedObjects: Set<string>){
    const objectsList = Array.from(detectedObjects).join(', ');
    return `${prompt}\n\nDetected objects in these frames: ${objectsList}\n\n`;
  }

  addAudioTranscript(prompt:string, transcripts:string){
    return `${prompt}\n\nAudio transcripts for this chunk of video:\n${transcripts}\n\n`;
  }


  getCaptionsSummarizeTemplate(): string {
    return CaptionsSummarizeTemplate;
  }

  getCaptionsReduceTemplate(): string {
    return CaptionsReduceTemplate;
  }

  getCaptionsReduceSingleTextTemplate(): string {
    return CaptionsReduceSingleTextTemplate;
  }

  getChunkSummarizeTemplate(): string {
    return ChunkSummarizeTemplate;
  }

  getChunkReduceTemplate(): string {
    return ChunkReduceTemplate;
  }

  getChunkReduceSingleTextTemplate(): string {
    return ChunkReduceSingleTextTemplate;
  }

  getFrameCaptionTemplateWithObjects(): string {
    return FrameCaptionTemplateWithObjects;
  }

  getFrameCaptionTemplateWithoutObjects(): string {
    return FrameCaptionTemplateWithoutObjects;
  }

  getMultipleFrameCaptionTemplateWithoutObjects(): string {
    return MultipleFrameCaptionTemplateWithoutObjects;
  }

  createUserQuery(template: string, data: string | string[]): string {
    const dataString = Array.isArray(data) ? data.join('\n\n') : data;
    return template.replaceAll('%data%', dataString);
  }
}
