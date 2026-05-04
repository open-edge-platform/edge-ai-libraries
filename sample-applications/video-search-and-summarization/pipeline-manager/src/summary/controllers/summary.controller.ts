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
  SummaryPipelineROSwagger,
} from '../models/summary-pipeline.model';
import { VideoService } from 'src/video-upload/services/video.service';
import { Video } from 'src/video-upload/models/video.model';
import { AppConfigService } from 'src/video-upload/services/app-config.service';
import { StateService } from 'src/state-manager/services/state.service';
import { State } from 'src/state-manager/models/state.model';
import { ApiBody, ApiCreatedResponse, ApiOkResponse, ApiOperation, ApiParam, ApiTags } from '@nestjs/swagger';
import { UiService } from 'src/state-manager/services/ui.service';
import { SummaryService } from '../services/summary.service';

@ApiTags('Summary')
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
  @ApiOperation({ summary: 'Get all summary states' })
  @ApiOkResponse({ description: 'Get all summary states raw' })
  getSummary(): State[] {
    return this.$state.fetchAll();
  }

  @Get('ui')
  @ApiOperation({ summary: 'Get summary list for UI' })
  @ApiOkResponse({ description: 'Get a list of summary states in UI-friendly format' })
  getSummaryList() {
    const states = this.$state.fetchAll();
    const uiStates = states.map((curr) => this.$ui.getUiState(curr.stateId));
    return uiStates;
  }

  @Get(':stateId')
  @ApiOperation({ summary: 'Get summary state by ID' })
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
  @ApiOperation({ summary: 'Get raw summary state by ID' })
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
  @ApiOperation({ summary: 'Start a video summary pipeline' })
  @ApiBody({ type: SummaryPipelineDTOSwagger })
  @ApiCreatedResponse({ description: 'Summary pipeline started', type: SummaryPipelineROSwagger })
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
      if (reqBody.prompts.audioSummaryMapPrompt) {
        systemConfig.audioSummaryMapPrompt = reqBody.prompts.audioSummaryMapPrompt;
      }
      if (reqBody.prompts.audioSummaryReducePrompt) {
        systemConfig.audioSummaryReducePrompt =
          reqBody.prompts.audioSummaryReducePrompt;
      }
      if (reqBody.prompts.audioSummarySinglePrompt) {
        systemConfig.audioSummarySinglePrompt =
          reqBody.prompts.audioSummarySinglePrompt;
      }
    }

    // Setup Audio Checks
    if (reqBody.audio && reqBody.audio.audioModel) {
      systemConfig.audioModel = reqBody.audio.audioModel;
      systemConfig.audioUseFullTranscriptSummary =
        reqBody.audio.useFullTranscriptSummary ?? systemConfig.audioUseFullTranscriptSummary;
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
  @ApiOperation({ summary: 'Delete a summary state' })
  @ApiParam({
    name: 'stateId',
    required: true,
    description: 'ID of the summary state to delete',
  })
  @ApiOkResponse({ description: 'Summary state deleted' })
  async deleteSummaryById(@Param() params: { stateId: string }) {
    const { stateId } = params;

    if (!this.$state.exists(stateId)) {
      throw new NotFoundException('State not found');
    }

    await this.$summary.removeSummary(stateId);

    return { message: 'State deleted successfully' };
  }
}
