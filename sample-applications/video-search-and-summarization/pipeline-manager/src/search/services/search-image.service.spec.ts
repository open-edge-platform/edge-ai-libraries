// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import {
  BadGatewayException,
  BadRequestException,
  NotFoundException,
  PayloadTooLargeException,
  UnprocessableEntityException,
  UnsupportedMediaTypeException,
} from '@nestjs/common';
import { SearchImageService } from './search-image.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { ConfigService } from '@nestjs/config';
import { SEARCH_IMAGE_MAX_BYTES } from '../model/search-image.model';

const IMAGE_ID = '3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11';

jest.mock('uuid', () => ({
  v4: jest.fn(() => '3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11'),
}));

const PNG = Buffer.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01,
]);
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
const WEBP = Buffer.concat([
  Buffer.from('RIFF'),
  Buffer.from([0x10, 0x00, 0x00, 0x00]),
  Buffer.from('WEBPVP8 '),
]);

const makeFile = (
  originalname: string,
  mimetype: string,
  buffer: Buffer,
): Express.Multer.File =>
  ({ originalname, mimetype, buffer, size: buffer.length }) as any;

describe('SearchImageService', () => {
  let service: SearchImageService;
  let datastore: jest.Mocked<DatastoreService>;
  let publicBaseUrl: string | undefined;

  const build = async () => {
    const datastoreMock = {
      bucket: 'video-summary',
      uploadBuffer: jest.fn().mockResolvedValue({ etag: 'e' }),
      statObject: jest.fn().mockResolvedValue({ size: 10 }),
      deleteObject: jest.fn().mockResolvedValue(undefined),
      getObjectBuffer: jest.fn().mockResolvedValue(PNG),
      getObjectRelativePath: jest.fn(
        (name: string) => `/video-summary/${name}`,
      ),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SearchImageService,
        { provide: DatastoreService, useValue: datastoreMock },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) =>
              key === 'gateway.publicBaseUrl' ? publicBaseUrl : undefined,
            ),
          },
        },
      ],
    }).compile();

    service = module.get(SearchImageService);
    datastore = module.get(DatastoreService);
  };

  beforeEach(async () => {
    publicBaseUrl = 'http://192.168.1.10:12345';
    await build();
  });

  describe('parseBaseUrl', () => {
    it.each([
      ['http://192.168.1.10:12345', 'http://192.168.1.10:12345'],
      ['https://vss.example.com/', 'https://vss.example.com'],
      ['https://vss.example.com/prefix/', 'https://vss.example.com/prefix'],
      ['  http://[::1]:12345  ', 'http://[::1]:12345'],
    ])('accepts %s', (value, expected) => {
      expect(SearchImageService.parseBaseUrl(value)).toBe(expected);
    });

    it.each([
      undefined,
      '',
      'http://:12345',
      '192.168.1.10:12345',
      'ftp://host',
      'http://user:pw@host',
      'http://host/?q=1',
      'not a url',
    ])('rejects %s', (value) => {
      expect(SearchImageService.parseBaseUrl(value)).toBeNull();
    });
  });

  describe('getPublicBaseUrl', () => {
    it('prefers the configured PM_PUBLIC_BASE_URL', () => {
      expect(service.getPublicBaseUrl({ host: 'attacker.example' })).toBe(
        'http://192.168.1.10:12345',
      );
    });

    describe('without PM_PUBLIC_BASE_URL', () => {
      beforeEach(async () => {
        publicBaseUrl = undefined;
        await build();
      });

      it('uses X-Forwarded-Host and X-Forwarded-Proto', () => {
        expect(
          service.getPublicBaseUrl({
            host: 'vss.local',
            'x-forwarded-host': '10.0.0.5:12345, proxy.internal',
            'x-forwarded-proto': 'https',
          }),
        ).toBe('https://10.0.0.5:12345');
      });

      it('falls back to Host over http', () => {
        expect(service.getPublicBaseUrl({ host: '10.0.0.5:12345' })).toBe(
          'http://10.0.0.5:12345',
        );
      });

      it('ignores an unknown X-Forwarded-Proto', () => {
        expect(
          service.getPublicBaseUrl({
            host: 'h:1',
            'x-forwarded-proto': 'javascript',
          }),
        ).toBe('http://h:1');
      });

      it.each(['evil.com/path', 'evil.com@x', 'h:1 x', 'h:123456', '-h', ''])(
        'rejects malformed host %s',
        (host) => {
          expect(service.getPublicBaseUrl({ host })).toBeNull();
        },
      );

      it('returns a gateway-relative imageUrl when no host is usable', async () => {
        const result = await service.upload(
          makeFile('a.png', 'image/png', PNG),
          { host: 'bad host' },
        );
        expect(result.imageUrl).toBe(
          `/datastore/video-summary/search-images/${IMAGE_ID}.png`,
        );
      });

      it('builds imageUrl from the request host', async () => {
        const result = await service.upload(
          makeFile('a.png', 'image/png', PNG),
          { host: '10.0.0.5:12345' },
        );
        expect(result.imageUrl).toBe(
          `http://10.0.0.5:12345/datastore/video-summary/search-images/${IMAGE_ID}.png`,
        );
      });
    });
  });

  describe('detectFormat', () => {
    it.each([
      ['jpeg', JPEG],
      ['png', PNG],
      ['webp', WEBP],
    ])('detects %s from magic bytes', (format, content) => {
      expect(SearchImageService.detectFormat(content)).toBe(format);
    });

    it.each([
      ['gif', Buffer.from('GIF89a......')],
      ['bmp', Buffer.from('BM..........')],
      ['text', Buffer.from('hello world!')],
      ['empty', Buffer.alloc(0)],
    ])('rejects %s', (_name, content) => {
      expect(SearchImageService.detectFormat(content)).toBeNull();
    });
  });

  describe('upload', () => {
    it.each([
      ['photo.jpg', 'image/jpeg', JPEG, 'jpg'],
      ['photo.JPEG', 'image/jpeg', JPEG, 'jpg'],
      ['photo.png', 'image/png', PNG, 'png'],
      ['photo.webp', 'image/webp', WEBP, 'webp'],
      ['photo.png', 'application/octet-stream', PNG, 'png'],
    ])(
      'stores %s (%s) and returns its URL',
      async (name, mime, content, ext) => {
        const result = await service.upload(makeFile(name, mime, content));

        const imageId = `${IMAGE_ID}.${ext}`;
        expect(datastore.uploadBuffer).toHaveBeenCalledWith(
          `search-images/${imageId}`,
          content,
          expect.stringMatching(/^image\//),
        );
        expect(result).toEqual({
          imageId,
          imageUrl: `http://192.168.1.10:12345/datastore/video-summary/search-images/${imageId}`,
          imagePath: `/datastore/video-summary/search-images/${imageId}`,
          contentType: expect.stringMatching(/^image\//),
          size: content.length,
        });
      },
    );

    it('rejects a missing file', async () => {
      await expect(service.upload(undefined)).rejects.toThrow(
        BadRequestException,
      );
    });

    it('rejects an empty file', async () => {
      await expect(
        service.upload(makeFile('a.png', 'image/png', Buffer.alloc(0))),
      ).rejects.toThrow(BadRequestException);
    });

    it.each(['a.gif', 'a.bmp', 'a.svg', 'a', 'a.png.exe'])(
      'rejects unsupported extension %s',
      async (name) => {
        await expect(
          service.upload(makeFile(name, 'image/png', PNG)),
        ).rejects.toThrow(UnsupportedMediaTypeException);
        expect(datastore.uploadBuffer).not.toHaveBeenCalled();
      },
    );

    it('rejects a mismatched declared content type', async () => {
      await expect(
        service.upload(makeFile('a.png', 'image/jpeg', PNG)),
      ).rejects.toThrow(UnsupportedMediaTypeException);
    });

    it('rejects content that does not match the extension', async () => {
      await expect(
        service.upload(makeFile('a.png', 'image/png', JPEG)),
      ).rejects.toThrow(UnsupportedMediaTypeException);
      expect(datastore.uploadBuffer).not.toHaveBeenCalled();
    });

    it('rejects an image over the size limit', async () => {
      const big = Buffer.concat([PNG, Buffer.alloc(SEARCH_IMAGE_MAX_BYTES)]);
      await expect(
        service.upload(makeFile('a.png', 'image/png', big)),
      ).rejects.toThrow(PayloadTooLargeException);
    });

    it('maps an object-store failure to 502', async () => {
      datastore.uploadBuffer.mockRejectedValueOnce(new Error('down'));
      await expect(
        service.upload(makeFile('a.png', 'image/png', PNG)),
      ).rejects.toThrow(BadGatewayException);
    });
  });

  describe('remove', () => {
    it('deletes a stored image', async () => {
      const result = await service.remove(`${IMAGE_ID}.png`);

      expect(datastore.deleteObject).toHaveBeenCalledWith(
        `search-images/${IMAGE_ID}.png`,
      );
      expect(result).toEqual({ imageId: `${IMAGE_ID}.png`, deleted: true });
    });

    it('returns 404 for an unknown image', async () => {
      datastore.statObject.mockResolvedValueOnce(null);
      await expect(service.remove(`${IMAGE_ID}.png`)).rejects.toThrow(
        NotFoundException,
      );
      expect(datastore.deleteObject).not.toHaveBeenCalled();
    });

    it.each(['../secret', `${IMAGE_ID}.gif`, `${IMAGE_ID}`, 'x.png'])(
      'rejects malformed id %s',
      async (imageId) => {
        await expect(service.remove(imageId)).rejects.toThrow(
          BadRequestException,
        );
        expect(datastore.statObject).not.toHaveBeenCalled();
      },
    );
  });

  describe('resolveImageId', () => {
    const id = `${IMAGE_ID}.png`;

    it.each([
      id,
      `http://minio-service:80/video-summary/search-images/${id}`,
      `http://192.168.1.10:4001/video-summary/search-images/${id}`,
      `/video-summary/search-images/${id}`,
      `http://host:12345/datastore/video-summary/search-images/${id}`,
      `/datastore/video-summary/search-images/${id}?x=1`,
    ])('accepts %s', (reference) => {
      expect(service.resolveImageId(reference)).toBe(id);
    });

    it.each([
      '',
      'not a url',
      `file:///video-summary/search-images/${id}`,
      `/other-bucket/search-images/${id}`,
      `/video-summary/other-prefix/${id}`,
      `/video-summary/search-images/${IMAGE_ID}/source.mp4`,
      `/video-summary/search-images/..%2F${id}`,
      `/video-summary/search-images/${id}/extra`,
    ])('rejects %s', (reference) => {
      expect(() => service.resolveImageId(reference)).toThrow(
        BadRequestException,
      );
    });
  });

  describe('resolveToDataUrl', () => {
    it('returns the stored image as a data URL', async () => {
      const result = await service.resolveToDataUrl(
        `/video-summary/search-images/${IMAGE_ID}.png`,
      );

      expect(datastore.getObjectBuffer).toHaveBeenCalledWith(
        `search-images/${IMAGE_ID}.png`,
        SEARCH_IMAGE_MAX_BYTES,
      );
      expect(result).toBe(`data:image/png;base64,${PNG.toString('base64')}`);
    });

    it('returns 404 when the image was deleted', async () => {
      datastore.getObjectBuffer.mockRejectedValueOnce({ code: 'NoSuchKey' });
      await expect(service.resolveToDataUrl(`${IMAGE_ID}.png`)).rejects.toThrow(
        NotFoundException,
      );
    });

    it('maps other object-store failures to 502', async () => {
      datastore.getObjectBuffer.mockRejectedValueOnce(new Error('down'));
      await expect(service.resolveToDataUrl(`${IMAGE_ID}.png`)).rejects.toThrow(
        BadGatewayException,
      );
    });

    it('rejects stored content that is not the expected image type', async () => {
      datastore.getObjectBuffer.mockResolvedValueOnce(JPEG);
      await expect(service.resolveToDataUrl(`${IMAGE_ID}.png`)).rejects.toThrow(
        UnprocessableEntityException,
      );
    });
  });
});
