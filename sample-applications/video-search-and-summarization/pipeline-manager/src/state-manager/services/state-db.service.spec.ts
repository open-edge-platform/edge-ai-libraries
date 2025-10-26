// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { StateDbService } from './state-db.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { StateEntity } from '../models/state.entity';
import { ObjectLiteral, Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { EVAMPipelines } from 'src/evam/models/evam.model';
import { StateActionStatus } from '../models/state.model';

// Create a mock type for the Repository
type MockRepository<T extends ObjectLiteral = Object> = Partial<
  Record<keyof Repository<T>, jest.Mock>
>;

// Function to create a mock repository
const createMockRepository = <
  T extends ObjectLiteral = any,
>(): MockRepository<T> => ({
  findOne: jest.fn(),
  create: jest.fn(),
  save: jest.fn(),
  find: jest.fn(),
});

describe('StateDbService', () => {
  let service: StateDbService;
  let repository: MockRepository<StateEntity>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        StateDbService,
        {
          provide: getRepositoryToken(StateEntity),
          useFactory: createMockRepository,
        },
      ],
    }).compile();

    service = module.get<StateDbService>(StateDbService);
    repository = module.get<MockRepository<StateEntity>>(
      getRepositoryToken(StateEntity),
    );
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('addState', () => {
    it('should successfully create and save a new state', async () => {
      // Arrange
      const mockState: StateEntity = {
        stateId: 'test-state-id',
        title: 'Test Video Title',
        videoId: 'test-video-id',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        userInputs: {
          chunkDuration: 10,
          samplingFrame: 4,
          frameOverlap: 2,
          multiFrame: 1,
        },
        chunks: {},
        frames: {},
        frameSummaries: {},
        systemConfig: {
          evamPipeline: EVAMPipelines.BASIC_INGESTION,
          frameOverlap: 3,
          multiFrame: 3,
          framePrompt: 'framePrompt',
          summaryMapPrompt: 'mapPrompt',
          summaryReducePrompt: 'reducePrompt',
          summarySinglePrompt: 'singlePrompt',
          audioModel: 'whisper',
        },
        status: {
          dataStoreUpload: StateActionStatus.IN_PROGRESS,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
      };
      const mockCreatedState = { ...mockState, dbId: 1 };

      repository.create?.mockReturnValue(mockCreatedState);
      repository.save?.mockResolvedValue(mockCreatedState);

      // Act
      const result = await service.addState(mockState);

      // Assert
      expect(repository.create).toHaveBeenCalledWith(mockState);
      expect(repository.save).toHaveBeenCalledWith(mockCreatedState);
      expect(result).toEqual(mockCreatedState);
      expect(result.dbId).toBeDefined();
    });

    it('should throw an error if save fails', async () => {
      // Arrange
      const mockState: Partial<StateEntity> = {
        stateId: 'test-state-id',
      };

      repository.create?.mockReturnValue(mockState);
      repository.save?.mockRejectedValue(new Error('Save failed'));

      // Act & Assert
      await expect(service.addState(mockState as StateEntity)).rejects.toThrow(
        'Save failed',
      );
      expect(repository.create).toHaveBeenCalledWith(mockState);
      expect(repository.save).toHaveBeenCalled();
    });
  });

  describe('getState', () => {
    it('should return a state when it exists', async () => {
      // Arrange

      const mockState: StateEntity = {
        stateId: 'test-state-id',
        title: 'Test Video Title',
        videoId: 'test-video-id',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        userInputs: {
          chunkDuration: 10,
          samplingFrame: 4,
          frameOverlap: 2,
          multiFrame: 1,
        },
        chunks: {},
        frames: {},
        frameSummaries: {},
        systemConfig: {
          evamPipeline: EVAMPipelines.BASIC_INGESTION,
          frameOverlap: 3,
          multiFrame: 3,
          framePrompt: 'framePrompt',
          summaryMapPrompt: 'mapPrompt',
          summaryReducePrompt: 'reducePrompt',
          summarySinglePrompt: 'singlePrompt',
          audioModel: 'whisper',
        },
        status: {
          dataStoreUpload: StateActionStatus.IN_PROGRESS,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
      };

      repository.findOne?.mockResolvedValue(mockState);

      // Act
      const result = await service.getState('test-state-id');

      // Assert
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId: 'test-state-id' },
      });
      expect(result).toEqual(mockState);
    });

    it('should return null when state does not exist', async () => {
      // Arrange
      repository.findOne?.mockResolvedValue(null);

      // Act
      const result = await service.getState('non-existent-id');

      // Assert
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId: 'non-existent-id' },
      });
      expect(result).toBeNull();
    });

    it('should handle database errors properly', async () => {
      // Arrange
      repository.findOne?.mockRejectedValue(
        new Error('Database connection failed'),
      );

      // Act & Assert
      await expect(service.getState('test-state-id')).rejects.toThrow(
        'Database connection failed',
      );
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId: 'test-state-id' },
      });
    });
  });

  describe('updateState', () => {
    it('should update an existing state successfully', async () => {
      // Arrange
      const stateId = 'test-state-id';

      const existingState: StateEntity = {
        dbId: 1,
        stateId,
        title: 'Test Video Title',
        videoId: 'test-video-id',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        userInputs: {
          chunkDuration: 10,
          samplingFrame: 4,
          frameOverlap: 2,
          multiFrame: 1,
        },
        chunks: {},
        frames: {},
        frameSummaries: {},
        systemConfig: {
          evamPipeline: EVAMPipelines.BASIC_INGESTION,
          frameOverlap: 3,
          multiFrame: 3,
          framePrompt: 'framePrompt',
          summaryMapPrompt: 'mapPrompt',
          summaryReducePrompt: 'reducePrompt',
          summarySinglePrompt: 'singlePrompt',
          audioModel: 'whisper',
        },

        status: {
          dataStoreUpload: StateActionStatus.IN_PROGRESS,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
      };

      const stateUpdate = {
        status: {
          dataStoreUpload: StateActionStatus.COMPLETE,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
        summary: 'This is a test summary',
      };

      const expectedUpdatedState = {
        ...existingState,
        ...stateUpdate,
        updatedAt: expect.any(String), // Updated timestamp will change
      };

      repository.findOne?.mockResolvedValue(existingState);
      repository.save?.mockResolvedValue(expectedUpdatedState);

      // Act
      const result = await service.updateState(stateId, stateUpdate);

      // Assert
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId },
      });
      expect(repository.save).toHaveBeenCalledWith(
        expect.objectContaining({
          ...existingState,
          ...stateUpdate,
        }),
      );
      expect(result).toEqual(expectedUpdatedState);
    });

    it('should return null when trying to update a non-existent state', async () => {
      // Arrange
      const stateId = 'non-existent-id';
      const stateUpdate = { summary: 'This update should fail' };

      repository.findOne?.mockResolvedValue(null);

      // Act
      const result = await service.updateState(stateId, stateUpdate);

      // Assert
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId },
      });
      expect(repository.save).not.toHaveBeenCalled();
      expect(result).toBeNull();
    });

    it('should handle partial updates correctly', async () => {
      // Arrange
      const stateId = 'test-state-id';

      const existingState: StateEntity = {
        dbId: 1,
        stateId,
        title: 'Test Video Title',
        videoId: 'test-video-id',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        userInputs: {
          chunkDuration: 10,
          samplingFrame: 4,
          frameOverlap: 2,
          multiFrame: 1,
        },
        chunks: {},
        frames: {},
        frameSummaries: {},
        systemConfig: {
          evamPipeline: EVAMPipelines.BASIC_INGESTION,
          frameOverlap: 3,
          multiFrame: 3,
          framePrompt: 'framePrompt',
          summaryMapPrompt: 'mapPrompt',
          summaryReducePrompt: 'reducePrompt',
          summarySinglePrompt: 'singlePrompt',
          audioModel: 'whisper',
        },

        status: {
          dataStoreUpload: StateActionStatus.IN_PROGRESS,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
      };

      // Only updating one field
      const stateUpdate = {
        videoId: 'https://example.com/video.mp4',
      };

      const expectedUpdatedState = {
        ...existingState,
        ...stateUpdate,
        updatedAt: expect.any(String),
      };

      repository.findOne?.mockResolvedValue(existingState);
      repository.save?.mockResolvedValue(expectedUpdatedState);

      // Act
      const result = await service.updateState(stateId, stateUpdate);

      // Assert
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId },
      });
      expect(repository.save).toHaveBeenCalledWith(
        expect.objectContaining({
          ...existingState,
          ...stateUpdate,
        }),
      );
      expect(result).toEqual(expectedUpdatedState);
      expect(result?.videoId).toEqual('https://example.com/video.mp4');
    });

    it('should propagate errors from the repository during update', async () => {
      // Arrange
      const stateId = 'test-state-id';
      const existingState: StateEntity = {
        dbId: 1,
        stateId,
        title: 'Test Video Title',
        videoId: 'test-video-id',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        userInputs: {
          chunkDuration: 10,
          samplingFrame: 4,
          frameOverlap: 2,
          multiFrame: 1,
        },
        chunks: {},
        frames: {},
        frameSummaries: {},
        systemConfig: {
          evamPipeline: EVAMPipelines.BASIC_INGESTION,
          frameOverlap: 3,
          multiFrame: 3,
          framePrompt: 'framePrompt',
          summaryMapPrompt: 'mapPrompt',
          summaryReducePrompt: 'reducePrompt',
          summarySinglePrompt: 'singlePrompt',
          audioModel: 'whisper',
        },

        status: {
          dataStoreUpload: StateActionStatus.IN_PROGRESS,
          summarizing: StateActionStatus.IN_PROGRESS,
          chunking: StateActionStatus.IN_PROGRESS,
        },
      };

      const stateUpdate = { summary: 'Updated summary' };

      repository.findOne?.mockResolvedValue(existingState);
      repository.save?.mockRejectedValue(new Error('Update failed'));

      // Act & Assert
      await expect(service.updateState(stateId, stateUpdate)).rejects.toThrow(
        'Update failed',
      );
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { stateId },
      });
      expect(repository.save).toHaveBeenCalled();
    });
  });
});
