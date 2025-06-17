// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Module } from '@nestjs/common';
import { SearchStateService } from './services/search-state.service';
import { SearchController } from './controllers/search.controller';
import { SearchDbService } from './services/search-db.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { SearchEntity } from './model/search.entity';
import { SearchShimService } from './services/search-shim.service';
import { SearchDataPrepShimService } from './services/search-data-prep-shim.service';
import { HttpModule } from '@nestjs/axios';

@Module({
  providers: [
    SearchStateService,
    SearchDbService,
    SearchShimService,
    SearchDataPrepShimService,
  ],
  controllers: [SearchController],
  imports: [HttpModule, TypeOrmModule.forFeature([SearchEntity])],
  exports: [SearchDataPrepShimService],
})
export class SearchModule {}
