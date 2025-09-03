// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Injectable,
  Logger,
  NotFoundException,
  UnprocessableEntityException,
} from '@nestjs/common';
import { Video, VideoDTO } from '../models/video.model';
import { VideoValidatorService } from './video-validator.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { v4 as uuidv4 } from 'uuid';
import { unlink } from 'fs';
import { VideoDbService } from './video-db.service';
import { lastValueFrom } from 'rxjs';
import { TagsService } from './tags.service';
import { DataPrepShimService } from 'src/data-prep/services/data-prep-shim.service';
import { DataPrepMinioDTO } from 'src/data-prep/models/data-prep.models';

@Injectable()
export class VideoService {
  private videoMap: Map<string, Video> = new Map();

  constructor(
    private $validator: VideoValidatorService,
    private $datastore: DatastoreService,
    private $videoDb: VideoDbService,
    private $dataprep: DataPrepShimService,
    private $tags: TagsService,
  ) {}

  isStreamable(videoPath: string) {
    return this.$validator.isStreamable(videoPath);
  }

  async createSearchEmbeddings(videoId: string) {
    const video = await this.getVideo(videoId);

    if (!video) {
      throw new NotFoundException('Video not found');
    }

    if (!video.dataStore) {
      throw new UnprocessableEntityException(
        'Video not available in object store',
      );
    }

    const videoData: DataPrepMinioDTO = {
      bucket_name: video.dataStore.bucket,
      video_id: video.dataStore?.objectName,
      video_name: video.dataStore?.fileName,
      tags: video.tags || [],
    };

    return await lastValueFrom(this.$dataprep.createEmbeddings(videoData));
  }

  async uploadVideo(
    videoFilePath: string,
    videoFileName: string,
    videoData: VideoDTO,
  ): Promise<string> {
    Logger.log('Uploading video', videoFilePath, videoFileName, videoData);

    const videoId = uuidv4();

    const { objectPath } = this.$datastore.getObjectName(
      videoId,
      videoFileName,
    );

    try {
      await this.$datastore.uploadFile(objectPath, videoFilePath);
    } catch (error) {
      Logger.error('Error uploading video file to object storage', error);
      throw new UnprocessableEntityException(
        'Error uploading video file to object storage',
      );
    }

    unlink(videoFilePath, (err) => {
      if (err) {
        Logger.error('Error deleting file', err);
      }
    });

    const video: Video = {
      name: videoFileName,
      tags: [],
      dataStore: {
        bucket: this.$datastore.bucket,
        fileName: videoFileName,
        objectName: videoId,
      },
      videoId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      url: objectPath,
    };

    let tagsToAdd: string[] = [];

    if (videoData.tagsArray && videoData.tagsArray.length > 0) {
      video.tags = videoData.tagsArray;
      tagsToAdd = videoData.tagsArray;
    }

    if (videoData.name) {
      video.name = videoData.name;
    }

    try {
      const videoDB = await this.$videoDb.create(video);
      if (tagsToAdd.length > 0) {
        Logger.log('Adding video tags', tagsToAdd);
        await this.$tags.addTags(tagsToAdd);
      }
      this.videoMap.set(video.videoId, videoDB);
    } catch (error) {
      Logger.error('Error saving video to database', error);
      throw new UnprocessableEntityException('Error saving video to database');
    }

    return videoId;
  }

  async getVideos(): Promise<Video[]> {
    const videoList = await this.$videoDb.readAll();

    for (const video of videoList) {
      this.videoMap.set(video.videoId, video);
    }

    return videoList ?? [];
  }

  async getVideo(videoId: string): Promise<Video | null> {
    if (this.videoMap.has(videoId)) {
      return this.videoMap.get(videoId) ?? null;
    }
    const video = await this.$videoDb.read(videoId);

    if (video) {
      this.videoMap.set(videoId, video);
    }

    return video ?? null;
  }
}
