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
}
