// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadRequestException,
  Controller,
  Delete,
  Headers,
  Param,
  Post,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { IncomingHttpHeaders } from 'http';
import {
  ApiBadRequestResponse,
  ApiBody,
  ApiConsumes,
  ApiCreatedResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiPayloadTooLargeResponse,
  ApiTags,
  ApiUnsupportedMediaTypeResponse,
} from '@nestjs/swagger';
import { memoryStorage } from 'multer';
import { FeaturesService } from 'src/features/features.service';
import {
  SEARCH_IMAGE_MAX_BYTES,
  SearchImageDeleteRO,
  SearchImageRO,
  SearchImageUploadDTO,
} from '../model/search-image.model';
import { SearchImageService } from '../services/search-image.service';

@ApiTags('Search')
@Controller('search/images')
export class SearchImageController {
  constructor(
    private $searchImage: SearchImageService,
    private $feature: FeaturesService,
  ) {}

  @Post('')
  @ApiOperation({
    summary: 'Upload a query image for search-by-image',
    description:
      'Stores the image in the object store and returns its gateway URL ' +
      '(`PM_PUBLIC_BASE_URL`, else the request host). Pass ' +
      '`imageUrl` to `POST /search` or `POST /search/query` to search by ' +
      'it instead of sending base64 image data.',
  })
  @ApiConsumes('multipart/form-data')
  @ApiBody({ type: SearchImageUploadDTO })
  @ApiCreatedResponse({ type: SearchImageRO })
  @ApiBadRequestResponse({
    description: 'No file, empty file, or image search not supported',
  })
  @ApiPayloadTooLargeResponse({ description: 'Image larger than 2 MB' })
  @ApiUnsupportedMediaTypeResponse({
    description: 'Not a JPEG, PNG or WebP image',
  })
  @UseInterceptors(
    FileInterceptor('image', {
      storage: memoryStorage(),
      limits: { fileSize: SEARCH_IMAGE_MAX_BYTES, files: 1 },
    }),
  )
  async uploadImage(
    @UploadedFile() file: Express.Multer.File,
    @Headers() headers: IncomingHttpHeaders,
  ): Promise<SearchImageRO> {
    if (!this.$feature.isImageSearchEnabled()) {
      throw new BadRequestException(
        'Image search is not supported in this deployment mode.',
      );
    }
    return await this.$searchImage.upload(file, headers);
  }

  @Delete(':imageId')
  @ApiOperation({ summary: 'Delete an uploaded query image' })
  @ApiParam({
    name: 'imageId',
    type: String,
    description: 'Image id returned by the upload',
  })
  @ApiOkResponse({ type: SearchImageDeleteRO })
  @ApiBadRequestResponse({ description: 'Malformed image id' })
  @ApiNotFoundResponse({ description: 'Image not found' })
  async deleteImage(
    @Param() params: { imageId: string },
  ): Promise<SearchImageDeleteRO> {
    return await this.$searchImage.remove(params.imageId);
  }
}
