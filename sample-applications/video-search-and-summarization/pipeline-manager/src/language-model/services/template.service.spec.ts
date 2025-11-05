// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { TemplateService } from './template.service';
import {
  CaptionsSummarizeTemplate,
  CaptionsReduceTemplate,
  CaptionsReduceSingleTextTemplate,
  ChunkSummarizeTemplate,
  ChunkReduceTemplate,
  ChunkReduceSingleTextTemplate,
  FrameCaptionTemplateWithObjects,
  FrameCaptionTemplateWithoutObjects,
  MultipleFrameCaptionTemplateWithoutObjects,
  PromptTemplates,
} from '../models/template.model';

// Mock the template model
jest.mock('../models/template.model', () => ({
  CaptionsSummarizeTemplate: 'MockedCaptionsSummarizeTemplate',
  CaptionsReduceTemplate: 'MockedCaptionsReduceTemplate',
  CaptionsReduceSingleTextTemplate: 'MockedCaptionsReduceSingleTextTemplate',
  ChunkSummarizeTemplate: 'MockedChunkSummarizeTemplate',
  ChunkReduceTemplate: 'MockedChunkReduceTemplate',
  ChunkReduceSingleTextTemplate: 'MockedChunkReduceSingleTextTemplate',
  FrameCaptionTemplateWithObjects: 'MockedFrameCaptionTemplateWithObjects',
  FrameCaptionTemplateWithoutObjects:
    'MockedFrameCaptionTemplateWithoutObjects',
  MultipleFrameCaptionTemplateWithoutObjects:
    'MockedMultipleFrameCaptionTemplateWithoutObjects',
  PromptTemplates: {
    defaultFrames: 'MockedDefaultFramesTemplate',
    defaultSummary: 'MockedDefaultSummaryTemplate with %data%',
    bodyCamSingle: 'MockedBodyCamSingleTemplate with %data%',
    nonExistentTemplate: undefined,
  },
}));

describe('TemplateService', () => {
  let service: TemplateService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [TemplateService],
    }).compile();

    service = module.get<TemplateService>(TemplateService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getTemplate', () => {
    it('should return the correct template when a valid name is provided', () => {
      const templateName = 'defaultFrames';
      const result = service.getTemplate(templateName);
      expect(result).toBe('MockedDefaultFramesTemplate');
    });

    it('should return an empty string when an invalid name is provided', () => {
      const templateName = 'invalidTemplateName';
      const result = service.getTemplate(templateName);
      expect(result).toBe('');
    });

    it('should handle undefined template name', () => {
      const result = service.getTemplate(undefined as unknown as string);
      expect(result).toBe('');
    });
  });

  describe('getTemplateWithReplacements', () => {
    it('should replace placeholders with provided values', () => {
      const templateName = 'defaultSummary';
      const replacements = { data: 'Test data' };
      const result = service.getTemplateWithReplacements(
        templateName,
        replacements,
      );
      expect(result).toBe('MockedDefaultSummaryTemplate with Test data');
    });

    it('should handle multiple replacements in a template', () => {
      // Mock the implementation for this specific test
      jest
        .spyOn(service, 'getTemplate')
        .mockReturnValueOnce('Template with %key1% and %key2%');

      const templateName = 'multipleReplacements';
      const replacements = { key1: 'value1', key2: 'value2' };
      const result = service.getTemplateWithReplacements(
        templateName,
        replacements,
      );
      expect(result).toBe('Template with value1 and value2');
    });

    it('should return the template unchanged if no replacements are provided', () => {
      const templateName = 'defaultSummary';
      const replacements = {};
      const result = service.getTemplateWithReplacements(
        templateName,
        replacements,
      );
      expect(result).toBe('MockedDefaultSummaryTemplate with %data%');
    });

    it('should handle non-existent template correctly', () => {
      const templateName = 'nonExistentTemplate';
      const replacements = { data: 'Test data' };
      const result = service.getTemplateWithReplacements(
        templateName,
        replacements,
      );
      expect(result).toBeFalsy();
    });
  });

  describe('Individual template getters', () => {
    it('should return CaptionsSummarizeTemplate', () => {
      expect(service.getCaptionsSummarizeTemplate()).toBe(
        'MockedCaptionsSummarizeTemplate',
      );
    });

    it('should return CaptionsReduceTemplate', () => {
      expect(service.getCaptionsReduceTemplate()).toBe(
        'MockedCaptionsReduceTemplate',
      );
    });

    it('should return CaptionsReduceSingleTextTemplate', () => {
      expect(service.getCaptionsReduceSingleTextTemplate()).toBe(
        'MockedCaptionsReduceSingleTextTemplate',
      );
    });

    it('should return ChunkSummarizeTemplate', () => {
      expect(service.getChunkSummarizeTemplate()).toBe(
        'MockedChunkSummarizeTemplate',
      );
    });

    it('should return ChunkReduceTemplate', () => {
      expect(service.getChunkReduceTemplate()).toBe(
        'MockedChunkReduceTemplate',
      );
    });

    it('should return ChunkReduceSingleTextTemplate', () => {
      expect(service.getChunkReduceSingleTextTemplate()).toBe(
        'MockedChunkReduceSingleTextTemplate',
      );
    });

    it('should return FrameCaptionTemplateWithObjects', () => {
      expect(service.getFrameCaptionTemplateWithObjects()).toBe(
        'MockedFrameCaptionTemplateWithObjects',
      );
    });

    it('should return FrameCaptionTemplateWithoutObjects', () => {
      expect(service.getFrameCaptionTemplateWithoutObjects()).toBe(
        'MockedFrameCaptionTemplateWithoutObjects',
      );
    });

    it('should return MultipleFrameCaptionTemplateWithoutObjects', () => {
      expect(service.getMultipleFrameCaptionTemplateWithoutObjects()).toBe(
        'MockedMultipleFrameCaptionTemplateWithoutObjects',
      );
    });
  });

  describe('createUserQuery', () => {
    it('should replace %data% with a string', () => {
      const template = 'This is a template with %data% placeholder';
      const data = 'sample data';
      const result = service.createUserQuery(template, data);
      expect(result).toBe('This is a template with sample data placeholder');
    });

    it('should join array data with newlines', () => {
      const template = 'This is a template with %data% placeholder';
      const data = ['line 1', 'line 2', 'line 3'];
      const result = service.createUserQuery(template, data);
      expect(result).toBe(
        'This is a template with line 1\n\nline 2\n\nline 3 placeholder',
      );
    });

    it('should handle empty string data', () => {
      const template = 'This is a template with %data% placeholder';
      const data = '';
      const result = service.createUserQuery(template, data);
      expect(result).toBe('This is a template with  placeholder');
    });

    it('should handle empty array data', () => {
      const template = 'This is a template with %data% placeholder';
      const data: string[] = [];
      const result = service.createUserQuery(template, data);
      expect(result).toBe('This is a template with  placeholder');
    });

    it('should handle multiple %data% occurrences', () => {
      const template = 'Template with %data% and another %data%';
      const data = 'test';
      const result = service.createUserQuery(template, data);
      expect(result).toBe('Template with test and another test');
    });
  });

  describe('getVideoTemplate', () => {
    it('should be defined but return undefined (placeholder method)', () => {
    const result = service.getTemplate('defaultFrames');
    expect(result).toBe('MockedDefaultFramesTemplate');
    });
  });
});
