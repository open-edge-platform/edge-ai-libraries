// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Body,
  Controller,
  Get,
  NotFoundException,
  Param,
  Post,
  UnprocessableEntityException,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { Video, VideoDTO, VideoRO } from '../models/video.model';
import { VideoService } from '../services/video.service';
import { FileInterceptor } from '@nestjs/platform-express';
import { FeaturesService } from '../../features/features.service';
import {
  ApiBody,
  ApiConsumes,
  ApiOperation,
  ApiParam,
  ApiResponse,
} from '@nestjs/swagger';
import { VideoDTOSwagger } from '../models/video.swagger';
import { FEATURE_STATE } from '../../features/features.model';
import { VideoValidatorService } from '../services/video-validator.service';

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
  @ApiResponse({
    status: 200,
    description: 'Returns a list of videos',
  })
  async getVideos(): Promise<{ videos: Video[] }> {
    const videos = await this.$video.getVideos();
    return { videos };
  }

  @Post('search-embeddings/:videoId')
  @ApiOperation({ summary: 'Create search embeddings for a video' })
  @ApiParam({
    name: 'videoId',
    type: String,
    description: 'ID of the video to create search embeddings for',
  })
  async createSearchEmbeddings(@Param() params: { videoId: string }) {
    if (this.$feature.getFeatures().search === FEATURE_STATE.OFF) {
      throw new NotFoundException('Search feature is disabled');
    }

    const embeddings = await this.$video.createSearchEmbeddings(params.videoId);

    if (embeddings.data?.status !== 'success') {
      throw new UnprocessableEntityException(
        'Error creating search embeddings',
      );
    }

    return embeddings.data;
  }
}
