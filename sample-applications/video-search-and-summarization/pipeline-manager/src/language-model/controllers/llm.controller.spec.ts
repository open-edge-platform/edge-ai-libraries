// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { LlmController } from './llm.controller';
import { LlmService } from '../services/llm.service';
import { TemplateService } from '../services/template.service';
import { Response } from 'express';
import { Subject } from 'rxjs';

describe('LlmController', () => {
  let controller: LlmController;
  let llmService: LlmService;
  let templateService: TemplateService;

  // Mock response object
  const mockResponse = () => {
    const res: Partial<Response> = {
      setHeader: jest.fn().mockReturnThis(),
      status: jest.fn().mockReturnThis(),
      send: jest.fn().mockReturnThis(),
      write: jest.fn().mockReturnThis(),
      end: jest.fn().mockReturnThis(),
    };
    return res as Response;
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [LlmController],
      providers: [
        {
          provide: LlmService,
          useValue: {
            summarizeMapReduce: jest.fn(),
          },
        },
        {
          provide: TemplateService,
          useValue: {
            getCaptionsSummarizeTemplate: jest
              .fn()
              .mockReturnValue('summary-template'),
            getCaptionsReduceTemplate: jest
              .fn()
              .mockReturnValue('reduce-template'),
            getCaptionsReduceSingleTextTemplate: jest
              .fn()
              .mockReturnValue('single-text-template'),
          },
        },
      ],
    }).compile();

    controller = module.get<LlmController>(LlmController);
    llmService = module.get<LlmService>(LlmService);
    templateService = module.get<TemplateService>(TemplateService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('textInference', () => {
    it('should process texts and stream the response', async () => {
      // Arrange
      const texts = ['text1', 'text2'];
      const response = mockResponse();

      // Mock summarizeMapReduce to simulate successful streaming
      (llmService.summarizeMapReduce as jest.Mock).mockImplementation(
        (_, __, ___, ____, streamer: Subject<string>) => {
          streamer.next('chunk 1');
          streamer.next('chunk 2');
          streamer.complete();
          return Promise.resolve();
        },
      );

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(templateService.getCaptionsSummarizeTemplate).toHaveBeenCalled();
      expect(templateService.getCaptionsReduceTemplate).toHaveBeenCalled();
      expect(
        templateService.getCaptionsReduceSingleTextTemplate,
      ).toHaveBeenCalled();

      expect(llmService.summarizeMapReduce).toHaveBeenCalledWith(
        texts,
        'summary-template',
        'reduce-template',
        'single-text-template',
        expect.any(Subject),
      );

      expect(response.setHeader).toHaveBeenCalledWith(
        'Content-Type',
        'application/json',
      );
      expect(response.setHeader).toHaveBeenCalledWith(
        'Transfer-Encoding',
        'chunked',
      );
      expect(response.write).toHaveBeenCalledTimes(2);
      expect(response.write).toHaveBeenNthCalledWith(1, 'chunk 1');
      expect(response.write).toHaveBeenNthCalledWith(2, 'chunk 2');
      expect(response.end).toHaveBeenCalled();
    });

    it('should handle streaming errors', async () => {
      // Arrange
      const texts = ['text1', 'text2'];
      const response = mockResponse();
      const testError = new Error('Test error');

      // Mock summarizeMapReduce to simulate an error during streaming
      (llmService.summarizeMapReduce as jest.Mock).mockImplementation(
        (_, __, ___, ____, streamer: Subject<string>) => {
          streamer.error(testError);
          return Promise.resolve();
        },
      );

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(response.status).toHaveBeenCalledWith(500);
      expect(response.send).toHaveBeenCalledWith(testError.message);
    });

    it('should handle exceptions thrown during processing', async () => {
      // Arrange
      const texts = ['text1', 'text2'];
      const response = mockResponse();
      const testError = new Error('Processing failed');

      // Mock summarizeMapReduce to throw an error
      (llmService.summarizeMapReduce as jest.Mock).mockRejectedValue(testError);

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(response.status).toHaveBeenCalledWith(500);
      expect(response.send).toHaveBeenCalledWith(testError);
    });

    it('should handle empty text array input', async () => {
      // Arrange
      const texts: string[] = [];
      const response = mockResponse();

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(llmService.summarizeMapReduce).toHaveBeenCalledWith(
        [],
        expect.any(String),
        expect.any(String),
        expect.any(String),
        expect.any(Subject),
      );
    });

    it('should correctly accumulate streaming response', async () => {
      // Arrange
      const texts = ['text1'];
      const response = mockResponse();

      // Mock summarizeMapReduce to simulate multiple streaming chunks
      (llmService.summarizeMapReduce as jest.Mock).mockImplementation(
        (_, __, ___, ____, streamer: Subject<string>) => {
          streamer.next('chunk ');
          streamer.next('by ');
          streamer.next('chunk');
          streamer.complete();
          return Promise.resolve();
        },
      );

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(response.write).toHaveBeenCalledTimes(3);
      expect(response.write).toHaveBeenNthCalledWith(1, 'chunk ');
      expect(response.write).toHaveBeenNthCalledWith(2, 'by ');
      expect(response.write).toHaveBeenNthCalledWith(3, 'chunk');
      expect(response.end).toHaveBeenCalled();
    });

    it('should pass templates from template service to LLM service', async () => {
      // Arrange
      const texts = ['text1'];
      const response = mockResponse();
      const mockSummaryTemplate = 'custom-summary-template';
      const mockReduceTemplate = 'custom-reduce-template';
      const mockSingleTextTemplate = 'custom-single-text-template';

      // Setup template service to return custom templates
      jest
        .spyOn(templateService, 'getCaptionsSummarizeTemplate')
        .mockReturnValue(mockSummaryTemplate);
      jest
        .spyOn(templateService, 'getCaptionsReduceTemplate')
        .mockReturnValue(mockReduceTemplate);
      jest
        .spyOn(templateService, 'getCaptionsReduceSingleTextTemplate')
        .mockReturnValue(mockSingleTextTemplate);

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(llmService.summarizeMapReduce).toHaveBeenCalledWith(
        texts,
        mockSummaryTemplate,
        mockReduceTemplate,
        mockSingleTextTemplate,
        expect.any(Subject),
      );
    });

    it('should log received texts and response', async () => {
      // Arrange
      const texts = ['text1', 'text2'];
      const response = mockResponse();

      // Spy on console.log
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      // Mock summarizeMapReduce
      (llmService.summarizeMapReduce as jest.Mock).mockImplementation(
        (_, __, ___, ____, streamer: Subject<string>) => {
          streamer.next('result text');
          streamer.complete();
          return Promise.resolve();
        },
      );

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(consoleLogSpy).toHaveBeenCalledWith('Received texts:', texts);
      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Setting up streamer subscription',
      );
      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Streamer subscription set up',
      );
      expect(consoleLogSpy).toHaveBeenCalledWith('result text');
      expect(consoleLogSpy).toHaveBeenCalledWith('result text'); // The final console.log of the accumulated response

      // Cleanup
      consoleLogSpy.mockRestore();
    });

    it('should log error when exception occurs', async () => {
      // Arrange
      const texts = ['text1'];
      const response = mockResponse();
      const testError = new Error('Test error');

      // Spy on console.error
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

      // Mock summarizeMapReduce to throw an error
      (llmService.summarizeMapReduce as jest.Mock).mockRejectedValue(testError);

      // Act
      await controller.textInference(texts, response);

      // Assert
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Error in textInference:',
        testError,
      );
      expect(response.status).toHaveBeenCalledWith(500);

      // Cleanup
      consoleErrorSpy.mockRestore();
    });
  });
});
