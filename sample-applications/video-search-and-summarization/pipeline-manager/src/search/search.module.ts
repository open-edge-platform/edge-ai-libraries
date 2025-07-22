// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { SearchStateService } from './services/search-state.service';
import { SearchController } from './controllers/search.controller';
import { SearchDbService } from './services/search-db.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { SearchEntity } from './model/search.entity';
import { SearchShimService } from './services/search-shim.service';
import { HttpModule } from '@nestjs/axios';
import { VideoUploadModule } from 'src/video-upload/video-upload.module';

@Module({
  providers: [SearchStateService, SearchDbService, SearchShimService],
  controllers: [SearchController],
  imports: [
    HttpModule,
    TypeOrmModule.forFeature([SearchEntity]),
    VideoUploadModule,
  ],
  exports: [],
})
export class SearchModule {}
