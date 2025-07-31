// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Body, Controller, Post } from '@nestjs/common';
import { VlmService } from '../services/vlm.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { TemplateService } from '../services/template.service';
import { FrameMetadata } from 'src/evam/models/message-broker.model';
import { ApiExcludeController } from '@nestjs/swagger';

export interface FrameData {
  frame: {
    metadata: FrameMetadata;
  };
}

export interface VLMPostDTO {
  imageUrl: string;
  template?: string; // Make template optional
  frameData?: FrameData;
}

@Controller('vlm')
@ApiExcludeController()
export class VlmController {
  constructor(
    private $vlm: VlmService,
    private $datastore: DatastoreService,
    private $template: TemplateService,
  ) {}

  @Post('')
  async imageInference(
    @Body('imageUrl') imageUrl: string,
    @Body('template') template?: string,
    @Body('frameData') frameData?: FrameData,
  ) {
    try {
      console.log(template, imageUrl, frameData);

      if (!template && !frameData) {
        throw new Error('Either template or frameData must be provided.');
      }

      let queryTemplate = template || '';

      if (frameData) {
        queryTemplate = this.$template.getFrameCaptionTemplateWithoutObjects();

        if (
          frameData.frame.metadata &&
          frameData.frame.metadata.objects &&
          frameData.frame.metadata.objects.length > 0
        ) {
          const objectDescriptions = frameData.frame.metadata.objects
            .map(
              (obj) =>
                `${obj.detection.label} with confidence score ${obj.detection.confidence}`,
            )
            .join(', ');
          queryTemplate = this.$template.createUserQuery(
            this.$template.getFrameCaptionTemplateWithObjects(),
            objectDescriptions,
          );
        }
      }

      const response = await this.$vlm.imageInference(queryTemplate, [
        imageUrl,
      ]);
      return response;
    } catch (error) {
      console.log(error);
      throw error;
    }
    // console.log(body);
  }
}
