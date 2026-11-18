// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { VideoEntity } from '../models/video.entity';
import { Repository } from 'typeorm';
import { Video } from '../models/video.model';

@Injectable()
export class VideoDbService {
  constructor(
    @InjectRepository(VideoEntity) private videoRepo: Repository<VideoEntity>,
  ) {}

  async create(video: Video): Promise<VideoEntity> {
    Logger.log('Adding video to database', video);

    const newVideo = this.videoRepo.create(video);
    return this.videoRepo.save(newVideo);
  }

  async readAll(): Promise<VideoEntity[]> {
    const videos = await this.videoRepo.find();
    return videos;
  }

  async read(videoId: string): Promise<VideoEntity | null> {
    const video = await this.videoRepo.findOne({
      where: { videoId },
    });
    return video ?? null;
  }

  async update(
    videoId: string,
    video: Partial<Video>,
  ): Promise<VideoEntity | null> {
    let existingVideo = await this.read(videoId);
    if (!existingVideo) {
      return null;
    }

    existingVideo = {
      ...existingVideo,
      ...video,
      updatedAt: new Date().toISOString(),
    };

    return this.videoRepo.save(existingVideo);
  }

  /**
   * Write only the given embedding-status columns. A targeted UPDATE rather
   * than `update()`'s read-modify-save, so concurrent writers (e.g. several
   * chunk-caption embeddings landing at once, or a tag merge) cannot clobber
   * each other's columns. `null` when the video does not exist.
   */
  async setEmbeddingFlags(
    videoId: string,
    flags: Partial<Pick<Video, 'textEmbeddings' | 'searchEmbeddings'>>,
  ): Promise<VideoEntity | null> {
    const result = await this.videoRepo.update(
      { videoId },
      { ...flags, updatedAt: new Date().toISOString() },
    );
    if (!result.affected) {
      return null;
    }
    return this.read(videoId);
  }

  async remove(videoId: string): Promise<boolean> {
    const result = await this.videoRepo.delete({ videoId });
    return (result.affected ?? 0) > 0;
  }
}
