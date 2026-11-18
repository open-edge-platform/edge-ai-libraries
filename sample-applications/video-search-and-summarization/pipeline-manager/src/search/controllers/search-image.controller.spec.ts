// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { SearchImageController } from './search-image.controller';
import { SearchImageService } from '../services/search-image.service';
import { FeaturesService } from 'src/features/features.service';

jest.mock('uuid', () => ({ v4: jest.fn(() => 'mock-uuid') }));

describe('SearchImageController', () => {
  let controller: SearchImageController;
  let searchImage: jest.Mocked<SearchImageService>;
  let features: jest.Mocked<FeaturesService>;

  const uploaded = {
    imageId: 'id.png',
    imageUrl:
      'http://192.168.1.10:12345/datastore/video-summary/search-images/id.png',
    imagePath: '/datastore/video-summary/search-images/id.png',
    contentType: 'image/png',
    size: 10,
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SearchImageController],
      providers: [
        {
          provide: SearchImageService,
          useValue: {
            upload: jest.fn().mockResolvedValue(uploaded),
            remove: jest
              .fn()
              .mockResolvedValue({ imageId: 'id.png', deleted: true }),
          },
        },
        {
          provide: FeaturesService,
          useValue: { isImageSearchEnabled: jest.fn().mockReturnValue(true) },
        },
      ],
    }).compile();

    controller = module.get(SearchImageController);
    searchImage = module.get(SearchImageService);
    features = module.get(FeaturesService);
  });

  it('uploads an image and returns its URL', async () => {
    const file = { originalname: 'a.png' } as Express.Multer.File;
    const headers = { host: '192.168.1.10:12345' };

    await expect(controller.uploadImage(file, headers)).resolves.toEqual(
      uploaded,
    );
    expect(searchImage.upload).toHaveBeenCalledWith(file, headers);
  });

  it('rejects uploads when image search is not supported', async () => {
    features.isImageSearchEnabled.mockReturnValueOnce(false);

    await expect(
      controller.uploadImage({} as Express.Multer.File, {}),
    ).rejects.toThrow(BadRequestException);
    expect(searchImage.upload).not.toHaveBeenCalled();
  });

  it('deletes an image by id', async () => {
    await expect(
      controller.deleteImage({ imageId: 'id.png' }),
    ).resolves.toEqual({ imageId: 'id.png', deleted: true });
    expect(searchImage.remove).toHaveBeenCalledWith('id.png');
  });
});
