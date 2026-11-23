// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { GeoService } from '../services/geo.service';
import { GeoIntersectionsRO } from '../models/geo.model';

@ApiTags('Geo')
@Controller('geo')
export class GeoController {
  constructor(private $geo: GeoService) {}

  @Get('intersections')
  @ApiOperation({
    summary:
      'Intersections with coordinates, from the API or the fallback file',
  })
  @ApiOkResponse({
    description:
      'Intersections keyed by intersection id, with source and staleness',
  })
  async getIntersections(): Promise<GeoIntersectionsRO> {
    return this.$geo.getIntersections();
  }
}
