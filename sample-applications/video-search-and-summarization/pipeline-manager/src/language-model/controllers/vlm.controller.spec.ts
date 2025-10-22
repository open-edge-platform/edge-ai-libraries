// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VlmController, FrameData, VLMPostDTO } from './vlm.controller';
import { VlmService } from '../services/vlm.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { TemplateService } from '../services/template.service';
import { FrameMetadata } from 'src/evam/models/message-broker.model';

// Create mock services
const mockVlmService = {
  imageInference: jest.fn(),
};

const mockDatastoreService = {
  // Add any methods that might be used in the controller
};

const mockTemplateService = {
  getFrameCaptionTemplateWithoutObjects: jest.fn(),
  getFrameCaptionTemplateWithObjects: jest.fn(),
  createUserQuery: jest.fn(),
};

describe('VlmController', () => {
  let controller: VlmController;
  let vlmService: VlmService;
  let templateService: TemplateService;

  beforeEach(async () => {
    // Reset mocks
    jest.clearAllMocks();
    
    const module: TestingModule = await Test.createTestingModule({
      controllers: [VlmController],
      providers: [
        { provide: VlmService, useValue: mockVlmService },
        { provide: DatastoreService, useValue: mockDatastoreService },
        { provide: TemplateService, useValue: mockTemplateService },
      ],
    }).compile();

    controller = module.get<VlmController>(VlmController);
    vlmService = module.get<VlmService>(VlmService);
    templateService = module.get<TemplateService>(TemplateService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('imageInference', () => {
    const imageUrl = 'http://example.com/image.jpg';
    const mockResponse = 'This is an image of a person walking';

    it('should process image with provided template', async () => {
      // Arrange
      const template = 'Describe what you see in this image';
      mockVlmService.imageInference.mockResolvedValueOnce(mockResponse);
      
      // Act
      const result = await controller.imageInference(imageUrl, template);
      
      // Assert
      expect(vlmService.imageInference).toHaveBeenCalledWith(template, [imageUrl]);
      expect(result).toBe(mockResponse);
    });

    it('should process image with frameData without objects', async () => {
      // Arrange
      const frameData: FrameData = {
        frame: {
          metadata: {} as FrameMetadata
        }
      };
      const templateWithoutObjects = 'Template without objects';
      mockTemplateService.getFrameCaptionTemplateWithoutObjects.mockReturnValueOnce(templateWithoutObjects);
      mockVlmService.imageInference.mockResolvedValueOnce(mockResponse);
      
      // Act
      const result = await controller.imageInference(imageUrl, undefined, frameData);
      
      // Assert
      expect(templateService.getFrameCaptionTemplateWithoutObjects).toHaveBeenCalled();
      expect(vlmService.imageInference).toHaveBeenCalledWith(templateWithoutObjects, [imageUrl]);
      expect(result).toBe(mockResponse);
    });

    it('should process image with frameData containing objects', async () => {
      // Arrange
      const frameData: FrameData = {
        frame: {
          metadata: {
            objects: [
              {
                detection: {
                  label: 'person',
                  confidence: 0.95
                }
              },
              {
                detection: {
                  label: 'car',
                  confidence: 0.88
                }
              }
            ]
          } as FrameMetadata
        }
      };
      
      const templateWithObjects = 'Template with objects: %data%';
      const modifiedTemplate = 'Template with objects: person with confidence score 0.95, car with confidence score 0.88';
      
      mockTemplateService.getFrameCaptionTemplateWithoutObjects.mockReturnValueOnce('Default template');
      mockTemplateService.getFrameCaptionTemplateWithObjects.mockReturnValueOnce(templateWithObjects);
      mockTemplateService.createUserQuery.mockReturnValueOnce(modifiedTemplate);
      mockVlmService.imageInference.mockResolvedValueOnce(mockResponse);
      
      // Act
      const result = await controller.imageInference(imageUrl, undefined, frameData);
      
      // Assert
      expect(templateService.getFrameCaptionTemplateWithObjects).toHaveBeenCalled();
      expect(templateService.createUserQuery).toHaveBeenCalledWith(
        templateWithObjects,
        'person with confidence score 0.95, car with confidence score 0.88'
      );
      expect(vlmService.imageInference).toHaveBeenCalledWith(modifiedTemplate, [imageUrl]);
      expect(result).toBe(mockResponse);
    });

    it('should throw an error if neither template nor frameData is provided', async () => {
      // Act & Assert
      await expect(controller.imageInference(imageUrl)).rejects.toThrow(
        'Either template or frameData must be provided.'
      );
      expect(vlmService.imageInference).not.toHaveBeenCalled();
    });

    it('should handle errors from the VLM service', async () => {
      // Arrange
      const template = 'Describe what you see in this image';
      const error = new Error('VLM service error');
      mockVlmService.imageInference.mockRejectedValueOnce(error);
      
      // Act & Assert
      await expect(controller.imageInference(imageUrl, template)).rejects.toThrow('VLM service error');
    });

    it('should log error and rethrow when exception occurs', async () => {
      // Arrange
      const template = 'Describe what you see in this image';
      const error = new Error('Some error');
      mockVlmService.imageInference.mockRejectedValueOnce(error);
      
      // Spy on console.log
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
      
      // Act & Assert
      await expect(controller.imageInference(imageUrl, template)).rejects.toThrow('Some error');
      expect(consoleSpy).toHaveBeenCalledWith(error);
      
      // Restore console.log
      consoleSpy.mockRestore();
    });
  });
});
