// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { ApiBody, ApiCreatedResponse, ApiOkResponse, ApiOperation, ApiParam, ApiTags } from '@nestjs/swagger';
import { ExampleDTO, ExampleROSwagger } from '../models/example.model';
import { ExampleService } from '../services/example.service';

@ApiTags('Example')
@Controller('example')
export class ExampleController {
  constructor(private $example: ExampleService) {}

  @Get(':exampleId')
  @ApiOperation({ summary: 'Get an example by ID' })
  @ApiParam({ name: 'exampleId', type: String, description: 'ID of the example item' })
  @ApiOkResponse({ description: 'Example details' })
  async getExample(@Param() params: { exampleId: string }) {
    return await this.$example.getExample(params.exampleId);
  }

  @Post('')
  @ApiOperation({ summary: 'Create an example item' })
  @ApiBody({ type: ExampleDTO })
  @ApiCreatedResponse({ description: 'Example item created', type: ExampleROSwagger })
  async createExample(@Body() reqBody: ExampleDTO) {
    return await this.$example.createExample(reqBody);
  }
}
