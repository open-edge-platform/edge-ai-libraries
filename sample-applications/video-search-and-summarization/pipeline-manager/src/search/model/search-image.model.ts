// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';

/** Object-store key prefix under which uploaded query images are kept. */
export const SEARCH_IMAGE_PREFIX = 'search-images';

/**
 * Upper bound on an uploaded query image, matching the search-by-image UI
 * limit (`MAX_IMAGE_SIZE_MB` in `ui/react/src/utils/constant.ts`).
 */
export const SEARCH_IMAGE_MAX_BYTES = 2 * 1024 * 1024;

export type SearchImageFormat = 'jpeg' | 'png' | 'webp';

/**
 * Formats accepted by search-by-image, matching the UI's
 * `acceptedImageFormats` / `plainAcceptedImageFormats`.
 */
export const SEARCH_IMAGE_FORMATS: Record<
  SearchImageFormat,
  { mimeType: string; extensions: string[]; storageExtension: string }
> = {
  jpeg: {
    mimeType: 'image/jpeg',
    extensions: ['.jpg', '.jpeg'],
    storageExtension: 'jpg',
  },
  png: { mimeType: 'image/png', extensions: ['.png'], storageExtension: 'png' },
  webp: {
    mimeType: 'image/webp',
    extensions: ['.webp'],
    storageExtension: 'webp',
  },
};

/** `<uuid v4>.<jpg|png|webp>`: the only shape an image id can take. */
export const SEARCH_IMAGE_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.(jpg|png|webp)$/;

export class SearchImageUploadDTO {
  @ApiProperty({
    type: 'string',
    format: 'binary',
    description:
      'Query image file (.jpg, .jpeg, .png or .webp; image/jpeg, image/png ' +
      'or image/webp) of at most 2 MB.',
  })
  image: any;
}

export class SearchImageRO {
  @ApiProperty({
    description: 'Identifier of the stored image; use it to delete the image.',
    example: '3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg',
  })
  imageId: string;

  @ApiProperty({
    description:
      'Externally reachable URL of the image through the nginx gateway ' +
      '(MinIO behind `/datastore`), based on `PM_PUBLIC_BASE_URL` or, when ' +
      'unset, the request host. Falls back to `imagePath` if no valid host ' +
      'is known. Pass it as `imageUrl` to `POST /search` or ' +
      '`POST /search/query` to search by this image.',
    example:
      'http://192.168.1.10:12345/datastore/video-summary/search-images/3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg',
  })
  imageUrl: string;

  @ApiProperty({
    description:
      'Gateway-relative path of the image; prefix with any address the ' +
      'caller uses to reach the gateway. Also accepted as `imageUrl`.',
    example:
      '/datastore/video-summary/search-images/3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg',
  })
  imagePath: string;

  @ApiProperty({ description: 'Detected MIME type', example: 'image/jpeg' })
  contentType: string;

  @ApiProperty({ description: 'Size in bytes', example: 48213 })
  size: number;
}

export class SearchImageDeleteRO {
  @ApiProperty({ example: '3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg' })
  imageId: string;

  @ApiProperty({ example: true })
  deleted: boolean;
}
