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
import { DatastoreModule } from 'src/datastore/datastore.module';
import { SearchImageService } from './services/search-image.service';
import { SearchImageController } from './controllers/search-image.controller';

@Module({
  providers: [
    SearchStateService,
    SearchDbService,
    SearchShimService,
    SearchImageService,
  ],
  // SearchImageController first so `search/images` is matched before the
  // `search/:queryId` routes.
  controllers: [SearchImageController, SearchController],
  imports: [
    HttpModule,
    TypeOrmModule.forFeature([SearchEntity]),
    VideoUploadModule,
    DatastoreModule,
  ],
  exports: [],
})
export class SearchModule {}
