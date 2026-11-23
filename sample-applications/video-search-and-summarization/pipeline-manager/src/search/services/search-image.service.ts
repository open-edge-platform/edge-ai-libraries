// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadGatewayException,
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
  PayloadTooLargeException,
  UnprocessableEntityException,
  UnsupportedMediaTypeException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { IncomingHttpHeaders } from 'http';
import * as path from 'path';
import { v4 as uuidV4 } from 'uuid';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import {
  SEARCH_IMAGE_FORMATS,
  SEARCH_IMAGE_ID_PATTERN,
  SEARCH_IMAGE_MAX_BYTES,
  SEARCH_IMAGE_PREFIX,
  SearchImageDeleteRO,
  SearchImageFormat,
  SearchImageRO,
} from '../model/search-image.model';

const SUPPORTED_EXTENSIONS = Object.values(SEARCH_IMAGE_FORMATS).flatMap(
  (format) => format.extensions,
);

/** MIME type a multipart client sends when it does not know the file type. */
const UNSPECIFIED_MIME_TYPE = 'application/octet-stream';

/** nginx gateway prefix under which the object store is exposed. */
const GATEWAY_DATASTORE_PREFIX = '/datastore';

/** `host`, `host:port`, or `[ipv6]:port`; rejects anything URL-breaking. */
const HOST_HEADER_PATTERN =
  /^(?:\[[0-9a-fA-F:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::\d{1,5})?$/;

function firstHeaderValue(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw ?? '').split(',')[0].trim();
}

/**
 * Stores query images in the object store and resolves them back for
 * search-by-image (claim-check pattern): clients upload once, then refer to
 * the image by URL instead of shipping base64 payloads on every request.
 */
@Injectable()
export class SearchImageService {
  private readonly configuredBaseUrl: string | null;

  constructor(
    private $datastore: DatastoreService,
    $config: ConfigService,
  ) {
    this.configuredBaseUrl = SearchImageService.parseBaseUrl(
      $config.get<string>('gateway.publicBaseUrl'),
    );
  }

  /** Validate `PM_PUBLIC_BASE_URL`; `null` (with a warning) when unusable. */
  static parseBaseUrl(value?: string | null): string | null {
    const trimmed = (value ?? '').trim();
    if (!trimmed) {
      return null;
    }
    try {
      const url = new URL(trimmed);
      if (
        (url.protocol === 'http:' || url.protocol === 'https:') &&
        url.hostname &&
        !url.username &&
        !url.password &&
        !url.search &&
        !url.hash
      ) {
        return `${url.origin}${url.pathname}`.replace(/\/+$/, '');
      }
    } catch {
      // fall through to the warning
    }
    Logger.warn(
      'Ignoring PM_PUBLIC_BASE_URL: expected an http(s) base URL such as http://<HOST_IP>:12345',
    );
    return null;
  }

  /**
   * Externally reachable gateway base URL for links returned to clients:
   * `PM_PUBLIC_BASE_URL` when set, otherwise derived from the proxied
   * request's `X-Forwarded-Proto` / `X-Forwarded-Host` (or `Host`) headers.
   * `null` when neither yields a well-formed origin.
   */
  getPublicBaseUrl(headers: IncomingHttpHeaders = {}): string | null {
    if (this.configuredBaseUrl) {
      return this.configuredBaseUrl;
    }
    const forwardedProto = firstHeaderValue(
      headers['x-forwarded-proto'],
    ).toLowerCase();
    const proto = forwardedProto === 'https' ? 'https' : 'http';
    const host =
      firstHeaderValue(headers['x-forwarded-host']) ||
      firstHeaderValue(headers.host);
    if (!HOST_HEADER_PATTERN.test(host)) {
      return null;
    }
    return `${proto}://${host}`;
  }

  /** Identify a supported image format from its magic bytes. */
  static detectFormat(content: Buffer): SearchImageFormat | null {
    if (
      content.length >= 3 &&
      content[0] === 0xff &&
      content[1] === 0xd8 &&
      content[2] === 0xff
    ) {
      return 'jpeg';
    }
    const pngSignature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
    if (
      content.length >= pngSignature.length &&
      pngSignature.every((byte, index) => content[index] === byte)
    ) {
      return 'png';
    }
    if (
      content.length >= 12 &&
      content.toString('ascii', 0, 4) === 'RIFF' &&
      content.toString('ascii', 8, 12) === 'WEBP'
    ) {
      return 'webp';
    }
    return null;
  }

  private objectName(imageId: string): string {
    return `${SEARCH_IMAGE_PREFIX}/${imageId}`;
  }

  private toRO(
    imageId: string,
    contentType: string,
    size: number,
    headers?: IncomingHttpHeaders,
  ): SearchImageRO {
    const imagePath = `${GATEWAY_DATASTORE_PREFIX}${this.$datastore.getObjectRelativePath(
      this.objectName(imageId),
    )}`;
    const baseUrl = this.getPublicBaseUrl(headers);
    return {
      imageId,
      imageUrl: baseUrl ? `${baseUrl}${imagePath}` : imagePath,
      imagePath,
      contentType,
      size,
    };
  }

  async upload(
    file?: Express.Multer.File,
    headers?: IncomingHttpHeaders,
  ): Promise<SearchImageRO> {
    if (!file || !file.buffer) {
      throw new BadRequestException(
        'An image file is required in the `image` form field.',
      );
    }

    const extension = path.extname(file.originalname ?? '').toLowerCase();
    const claimedFormat = (
      Object.keys(SEARCH_IMAGE_FORMATS) as SearchImageFormat[]
    ).find((format) =>
      SEARCH_IMAGE_FORMATS[format].extensions.includes(extension),
    );
    if (!claimedFormat) {
      throw new UnsupportedMediaTypeException(
        `Unsupported image extension. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}.`,
      );
    }

    const { mimeType, storageExtension } = SEARCH_IMAGE_FORMATS[claimedFormat];
    const declaredMime = (file.mimetype ?? '').toLowerCase();
    if (
      declaredMime &&
      declaredMime !== UNSPECIFIED_MIME_TYPE &&
      declaredMime !== mimeType
    ) {
      throw new UnsupportedMediaTypeException(
        `Content type ${declaredMime} does not match a ${extension} image (${mimeType}).`,
      );
    }

    const size = file.buffer.length;
    if (size === 0) {
      throw new BadRequestException('The image file is empty.');
    }
    if (size > SEARCH_IMAGE_MAX_BYTES) {
      throw new PayloadTooLargeException(
        `Image is too large. Maximum size is ${SEARCH_IMAGE_MAX_BYTES / (1024 * 1024)} MB.`,
      );
    }

    if (SearchImageService.detectFormat(file.buffer) !== claimedFormat) {
      throw new UnsupportedMediaTypeException(
        `File content is not a valid ${claimedFormat.toUpperCase()} image.`,
      );
    }

    const imageId = `${uuidV4()}.${storageExtension}`;
    try {
      await this.$datastore.uploadBuffer(
        this.objectName(imageId),
        file.buffer,
        mimeType,
      );
    } catch (error) {
      Logger.error('Failed to store search image', error);
      throw new BadGatewayException(
        'Could not store the image in the object store.',
      );
    }

    return this.toRO(imageId, mimeType, size, headers);
  }

  async remove(imageId: string): Promise<SearchImageDeleteRO> {
    if (!SEARCH_IMAGE_ID_PATTERN.test(imageId ?? '')) {
      throw new BadRequestException('Invalid image id.');
    }
    const objectName = this.objectName(imageId);

    const stat = await this.$datastore.statObject(objectName);
    if (!stat) {
      throw new NotFoundException(`Search image ${imageId} not found.`);
    }
    await this.$datastore.deleteObject(objectName);
    return { imageId, deleted: true };
  }

  /**
   * Map an image reference to its image id. Accepts a bare image id, or any
   * URL/path whose path is `[/datastore]/<bucket>/search-images/<imageId>`,
   * such as the returned `imageUrl`/`imagePath`. The host is ignored, since
   * callers reach the gateway by whatever address they can; only the path is
   * used, so a reference can never make the server fetch an arbitrary host
   * or object (no SSRF).
   */
  resolveImageId(reference: string): string {
    const invalid = new BadRequestException(
      'imageUrl must be an image URL or id returned by POST /search/images.',
    );
    const trimmed = (reference ?? '').trim();
    if (SEARCH_IMAGE_ID_PATTERN.test(trimmed)) {
      return trimmed;
    }

    let segments: string[];
    try {
      const url = new URL(trimmed, 'http://vss.invalid');
      if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        throw invalid;
      }
      segments = url.pathname
        .split('/')
        .filter((segment) => segment.length > 0)
        .map((segment) => decodeURIComponent(segment));
    } catch {
      throw invalid;
    }

    if (segments[0] === 'datastore') {
      segments.shift();
    }
    const [bucket, prefix, imageId, ...rest] = segments;
    if (
      rest.length > 0 ||
      bucket !== this.$datastore.bucket ||
      prefix !== SEARCH_IMAGE_PREFIX ||
      !SEARCH_IMAGE_ID_PATTERN.test(imageId ?? '')
    ) {
      throw invalid;
    }
    return imageId;
  }

  /**
   * Load a stored query image and return it as a `data:` URL, the form the
   * search-by-image pipeline already accepts.
   */
  async resolveToDataUrl(reference: string): Promise<string> {
    const imageId = this.resolveImageId(reference);

    let content: Buffer;
    try {
      content = await this.$datastore.getObjectBuffer(
        this.objectName(imageId),
        SEARCH_IMAGE_MAX_BYTES,
      );
    } catch (error) {
      if (DatastoreService.isNotFoundError(error)) {
        throw new NotFoundException(
          `Search image ${imageId} not found. Upload it with POST /search/images first.`,
        );
      }
      Logger.error(`Failed to read search image ${imageId}`, error);
      throw new BadGatewayException(
        'Could not read the image from the object store.',
      );
    }

    const format = SearchImageService.detectFormat(content);
    if (
      !format ||
      SEARCH_IMAGE_FORMATS[format].storageExtension !==
        path.extname(imageId).slice(1)
    ) {
      throw new UnprocessableEntityException(
        `Stored image ${imageId} is not a valid image.`,
      );
    }

    return `data:${SEARCH_IMAGE_FORMATS[format].mimeType};base64,${content.toString('base64')}`;
  }
}
