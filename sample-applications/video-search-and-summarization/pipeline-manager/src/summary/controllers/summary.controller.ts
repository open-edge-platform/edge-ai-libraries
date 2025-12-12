// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  InternalServerErrorException,
  NotFoundException,
  Param,
  Post,
} from '@nestjs/common';
import {
  SummaryPipelineDTO,
  SummaryPipelineDTOSwagger,
  SummaryPipelinRO,
} from '../models/summary-pipeline.model';
import { VideoService } from 'src/video-upload/services/video.service';
import { Video } from 'src/video-upload/models/video.model';
import { AppConfigService } from 'src/video-upload/services/app-config.service';
import { StateService } from 'src/state-manager/services/state.service';
import { State } from 'src/state-manager/models/state.model';
import { ApiBody, ApiOkResponse, ApiParam } from '@nestjs/swagger';
import { UiService } from 'src/state-manager/services/ui.service';
import { SummaryService } from '../services/summary.service';

@Controller('summary')
export class SummaryController {
  constructor(
    private $video: VideoService,
    private $appConfig: AppConfigService,
    private $state: StateService,
    private $ui: UiService,
    private $summary: SummaryService,
  ) {}

  @Get('')
  @ApiOkResponse({ description: 'Get all summary states raw' })
  getSummary(): State[] {
    return this.$state.fetchAll();
  }

  @Get('ui')
  @ApiOkResponse({ description: 'Get a list of summary ids' })
  getSummaryList() {
    const states = this.$state.fetchAll();
    const uiStates = states.map((curr) => this.$ui.getUiState(curr.stateId));
    return uiStates;
  }

  @Get(':stateId')
  @ApiParam({
    name: 'stateId',
    required: true,
    description: 'ID of the summary state',
  })
  @ApiOkResponse({ description: 'Get UI Friendly summary state by ID' })
  getSummaryById(@Param() params: { stateId: string }) {
    return this.$ui.getUiState(params.stateId);
  }

  @Get(':stateId/raw')
  @ApiParam({
    name: 'stateId',
    required: true,
    description: 'ID of the summary state to fetch raw data',
  })
  @ApiOkResponse({ description: 'Get raw summary state data by ID' })
  getSummaryRawById(@Param() params: { stateId: string }) {
    return this.$state.fetch(params.stateId);
  }

  @Post('')
  @ApiBody({ type: SummaryPipelineDTOSwagger })
  async startSummaryPipeline(
    @Body() reqBody: SummaryPipelineDTO,
  ): Promise<SummaryPipelinRO> {
    const { videoId } = reqBody;

    let video: Video | null = null;

    if (!reqBody.title) {
      throw new BadRequestException('Title is required');
    }

    if (videoId) {
      video = await this.$video.getVideo(videoId);

      if (!video) {
        throw new NotFoundException('Video not found');
      }
    }

    const systemConfig = this.$appConfig.systemConfig();

    if (reqBody.sampling.frameOverlap) {
      systemConfig.frameOverlap = reqBody.sampling.frameOverlap;
    }

    if (reqBody.sampling.multiFrame) {
      if (reqBody.sampling.multiFrame > +systemConfig.multiFrame) {
        throw new BadRequestException(
          `Current Maximum Supported Batch Size is ${systemConfig.multiFrame}.`,
        );
      }

      const actualMultiFrame =
        systemConfig.frameOverlap + reqBody.sampling.samplingFrame;

      if (actualMultiFrame !== reqBody.sampling.multiFrame) {
        throw new BadRequestException('Multi frame mismatch');
      }

      systemConfig.multiFrame = actualMultiFrame;
    } else {
      const actualMultiFrame =
        systemConfig.frameOverlap + reqBody.sampling.samplingFrame;
      systemConfig.multiFrame = actualMultiFrame;
    }

    // Setup EVAM Checks
    if (!reqBody.evam || !reqBody.evam.evamPipeline) {
      throw new BadRequestException('Evam pipeline not found');
    } else {
      systemConfig.evamPipeline = reqBody.evam.evamPipeline;
    }

    // Setup Prompt checks
    if (reqBody.prompts) {
      if (reqBody.prompts.framePrompt) {
        systemConfig.framePrompt = reqBody.prompts.framePrompt;
      }
      if (reqBody.prompts.summaryMapPrompt) {
        systemConfig.summaryMapPrompt = reqBody.prompts.summaryMapPrompt;
      }
      if (reqBody.prompts.summaryReducePrompt) {
        systemConfig.summaryReducePrompt = reqBody.prompts.summaryReducePrompt;
      }
      if (reqBody.prompts.summarySinglePrompt) {
        systemConfig.summarySinglePrompt = reqBody.prompts.summarySinglePrompt;
      }
    }

    // Setup Audio Checks
    if (reqBody.audio && reqBody.audio.audioModel) {
      systemConfig.audioModel = reqBody.audio.audioModel;
    }

    let stateId: string | null = null;

    if (video) {
      const state = await this.$state.create(
        video,
        reqBody.title,
        systemConfig,
        reqBody.sampling,
      );
      stateId = state.stateId;
    }

    if (!stateId) {
      throw new InternalServerErrorException('State creation failed');
    }

    return { summaryPipelineId: stateId };
  }

  @Delete(':stateId')
  @ApiParam({
    name: 'stateId',
    required: true,
    description: 'ID of the summary state to delete',
  })
  @ApiOkResponse({ description: 'Delete a summary state by ID' })
  async deleteSummaryById(@Param() params: { stateId: string }) {
    const { stateId } = params;

    if (!this.$state.exists(stateId)) {
      throw new NotFoundException('State not found');
    }

    await this.$summary.removeSummary(stateId);

    return { message: 'State deleted successfully' };
  }
}
