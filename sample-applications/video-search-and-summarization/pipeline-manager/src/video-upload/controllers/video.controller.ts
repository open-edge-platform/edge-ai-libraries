// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadGatewayException,
  Body,
  Controller,
  Get,
  Logger,
  NotFoundException,
  Param,
  Post,
  RequestTimeoutException,
  UnprocessableEntityException,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { AxiosError } from 'axios';
import { SearchEmbeddingsDTO, Video, VideoDTO, VideoRO } from '../models/video.model';
import { VideoService } from '../services/video.service';
import { FileInterceptor } from '@nestjs/platform-express';
import { FeaturesService } from '../../features/features.service';
import {
  ApiBody,
  ApiConsumes,
  ApiCreatedResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiTags,
} from '@nestjs/swagger';
import { VideoDTOSwagger } from '../models/video.swagger';
import { FEATURE_STATE } from '../../features/features.model';
import { VideoValidatorService } from '../services/video-validator.service';

@ApiTags('Video')
@Controller('videos')
export class VideoController {
  constructor(
    private $video: VideoService,
    private $feature: FeaturesService,
    private $videoValidator: VideoValidatorService,
  ) {}

  @Post('')
  @ApiOperation({ summary: 'Upload a video file' })
  @ApiConsumes('multipart/form-data')
  @ApiBody({ type: VideoDTOSwagger })
  @ApiCreatedResponse({ description: 'Video uploaded successfully' })
  @UseInterceptors(FileInterceptor('video'))
  async videoUpload(
    @UploadedFile() file: Express.Multer.File,
    @Body() reqBody: VideoDTO,
  ): Promise<VideoRO> {
    // Validate the file and request body
    if (!file) {
      throw new Error('File is required');
    }

    const streamable = await this.$videoValidator.isStreamable(file.path);

    if (!streamable) {
      throw new UnprocessableEntityException(
        'The video file is not streamable. Please upload a streamable MP4 video.',
      );
    }

    const parsedObject: VideoDTO = { name: file.filename, tagsArray: [] };

    if (reqBody.tags) {
      parsedObject.tagsArray = reqBody.tags
        .split(',')
        .map((curr) => curr.trim());
    }

    const videoId = await this.$video.uploadVideo(
      file.path,
      file.originalname,
      parsedObject,
    );

    const videoDataRO: VideoRO = {
      videoId,
    };

    return videoDataRO;
  }

  @Get(':videoId')
  @ApiOperation({ summary: 'Get a video by ID' })
  @ApiParam({ name: 'videoId', type: String, description: 'ID of the video' })
  @ApiOkResponse({ description: 'Video details' })
  async getVideo(
    @Param() params: { videoId: string },
  ): Promise<{ video: Video }> {
    const video = await this.$video.getVideo(params.videoId);

    if (!video) {
      throw new NotFoundException('Video not found');
    }

    return { video };
  }

  @Get('')
  @ApiOperation({ summary: 'Get all videos' })
  @ApiOkResponse({ description: 'Returns a list of videos' })
  async getVideos(): Promise<{ videos: Video[] }> {
    const videos = await this.$video.getVideos();
    return { videos };
  }

  @Post('search-embeddings/:videoId')
  @ApiOperation({ summary: 'Create search embeddings for a video' })
  @ApiBody({
    required: false,
    schema: {
      type: 'object',
      properties: {
        tags: {
          type: 'string',
          example: 'outdoor,daytime',
          description: 'Optional comma-separated tags to merge into existing video tags before embedding',
        },
      },
    },
  })
  @ApiParam({
    name: 'videoId',
    type: String,
    description: 'ID of the video to create search embeddings for',
  })
  @ApiCreatedResponse({ description: 'Search embeddings creation started' })
  async createSearchEmbeddings(
    @Param() params: { videoId: string },
    @Body() reqBody: SearchEmbeddingsDTO = {},
  ) {
    if (this.$feature.getFeatures().search === FEATURE_STATE.OFF) {
      throw new NotFoundException('Search feature is disabled');
    }

    const tagsArray = reqBody.tags
      ? reqBody.tags
          .split(',')
          .map((curr) => curr.trim())
          .filter((curr) => curr.length > 0)
      : [];

    let embeddings: { data?: { status?: string } };
    try {
      embeddings = await this.$video.createSearchEmbeddings(
        params.videoId,
        tagsArray,
      );
    } catch (error) {
      // Surface the real cause instead of a generic 500 so the UI can
      // distinguish a true timeout from a backend (e.g. model load) failure.
      if (error instanceof AxiosError) {
        const isTimeout =
          error.code === 'ECONNABORTED' || /timeout/i.test(error.message);
        const upstreamMessage =
          (error.response?.data as { message?: string } | undefined)?.message ||
          error.message;

        Logger.error(
          `Data-prep embedding request failed for video ${params.videoId}: ${upstreamMessage}`,
        );

        if (isTimeout) {
          throw new RequestTimeoutException(
            'Timed out while creating search embeddings',
          );
        }

        throw new BadGatewayException(
          `Data-prep failed to create embeddings: ${upstreamMessage}`,
        );
      }
      throw error;
    }

    if (embeddings.data?.status !== 'success') {
      throw new UnprocessableEntityException(
        'Error creating search embeddings',
      );
    }

    return embeddings.data;
  }
}
