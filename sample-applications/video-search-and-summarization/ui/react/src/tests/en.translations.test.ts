// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { enTranslations } from '../utils/i18n/translations/en';

describe('English translations test suite', () => {
  it('should export enTranslations as an object', () => {
    expect(typeof enTranslations).toBe('object');
    expect(enTranslations).not.toBeNull();
  });

  describe('Brand translations', () => {
    it('should have VideoSummary translation', () => {
      expect(enTranslations.VideoSummary).toBe('Video Summarization');
    });

    it('should have VSSBrand translation', () => {
      expect(enTranslations.VSSBrand).toBe('Video Summarization & Search');
    });

    it('should have VSearchBrand translation', () => {
      expect(enTranslations.VSearchBrand).toBe('Video Search');
    });

    it('should have VSummBrand translation', () => {
      expect(enTranslations.VSummBrand).toBe('Video Summarization');
    });
  });

  describe('Search-related translations', () => {
    it('should have SearchVideo translation', () => {
      expect(enTranslations.SearchVideo).toBe('Search Videos');
    });

    it('should have videoSearchStart translation', () => {
      expect(enTranslations.videoSearchStart).toBe('Video Search Query');
    });

    it('should have SearchingForPlaceholder translation', () => {
      expect(enTranslations.SearchingForPlaceholder).toBe('Red bus or white plane...');
    });

    it('should have search translation', () => {
      expect(enTranslations.search).toBe('Search');
    });

    it('should have searchNothingSelected translation', () => {
      expect(enTranslations.searchNothingSelected).toBe('Create a search query');
    });
  });

  describe('Upload and processing translations', () => {
    it('should have uploadingVideo translation', () => {
      expect(enTranslations.uploadingVideo).toBe('Uploading Video');
    });

    it('should have CreatingEmbedding translation', () => {
      expect(enTranslations.CreatingEmbedding).toBe('Creating Embedding');
    });

    it('should have TriggeringPipeline translation', () => {
      expect(enTranslations.TriggeringPipeline).toBe('Triggering Pipeline');
    });

    it('should have allDone translation', () => {
      expect(enTranslations.allDone).toBe('All Done');
    });
  });

  describe('Status and state translations', () => {
    it('should have naTag translation', () => {
      expect(enTranslations.naTag).toBe('N/A');
    });

    it('should have readyTag translation', () => {
      expect(enTranslations.readyTag).toBe('In Queue');
    });

    it('should have completeTag translation', () => {
      expect(enTranslations.completeTag).toBe('Completed');
    });

    it('should have progressTag translation', () => {
      expect(enTranslations.progressTag).toBe('In Progress');
    });
  });

  describe('Action button translations', () => {
    it('should have cancel translation', () => {
      expect(enTranslations.cancel).toBe('Cancel');
    });

    it('should have delete translation', () => {
      expect(enTranslations.delete).toBe('Delete');
    });

    it('should have submit translation', () => {
      expect(enTranslations.submit).toBe('Submit');
    });

    it('should have Submit translation', () => {
      expect(enTranslations.Submit).toBe('Apply');
    });

    it('should have confirm translation', () => {
      expect(enTranslations.confirm).toBe('Confirm');
    });
  });

  describe('Notification type translations', () => {
    it('should have success translation', () => {
      expect(enTranslations.success).toBe('success');
    });

    it('should have error translation', () => {
      expect(enTranslations.error).toBe('error');
    });

    it('should have warning translation', () => {
      expect(enTranslations.warning).toBe('warning');
    });

    it('should have info translation', () => {
      expect(enTranslations.info).toBe('info');
    });
  });

  describe('Template string translations', () => {
    it('should have sampleRate template string', () => {
      expect(enTranslations.sampleRate).toBe('Sample Rate: {{frames}} frames every {{interval}} seconds');
    });

    it('should have aiModel template string', () => {
      expect(enTranslations.aiModel).toBe('Model: {{model}}');
    });

    it('should have runningOn template string', () => {
      expect(enTranslations.runningOn).toBe('Running on: {{device}}');
    });

    it('should have frameOverlap template string', () => {
      expect(enTranslations.frameOverlap).toBe('Frame Overlap: {{overlap}}');
    });

    it('should have multiFrame template string', () => {
      expect(enTranslations.multiFrame).toBe('Multi Frames: {{multiFrame}}');
    });
  });

  describe('Error message translations', () => {
    it('should have summaryDeleteFailed translation', () => {
      expect(enTranslations.summaryDeleteFailed).toBe('Unable to delete summary');
    });

    it('should have videoUploadError translation', () => {
      expect(enTranslations.videoUploadError).toBe('An error occurred during video upload');
    });

    it('should have unknownError translation', () => {
      expect(enTranslations.unknownError).toBe('An unknown error occurred');
    });

    it('should have unexpectedError translation', () => {
      expect(enTranslations.unexpectedError).toBe('Unexpected error occurred');
    });

    it('should have serverError translation', () => {
      expect(enTranslations.serverError).toBe('Server error occured');
    });

    it('should have timeoutError translation', () => {
      expect(enTranslations.timeoutError).toBe(
        'Request timed out while processing the video. Please try again.',
      );
    });
  });

  describe('File and media related translations', () => {
    it('should have OnlyStreamableMp4 translation', () => {
      expect(enTranslations.OnlyStreamableMp4).toBe('Only mp4 videos are accepted');
    });

    it('should have StreamableHelpText translation', () => {
      expect(enTranslations.StreamableHelpText).toBe('Mp4 videos need to be streamble to be processed. ffmpeg can be used to make mp4 streamable using following command');
    });

    it('should have fileNotFound translation', () => {
      expect(enTranslations.fileNotFound).toBe('File not found');
    });

    it('should have invalidLink translation', () => {
      expect(enTranslations.invalidLink).toBe('Invalid link');
    });
  });

  describe('Setting related translations', () => {
    it('should have IngestionSettings translation', () => {
      expect(enTranslations.IngestionSettings).toBe('Ingestion Settings');
    });

    it('should have AudioSettings translation', () => {
      expect(enTranslations.AudioSettings).toBe('Audio Settings');
    });

    it('should have PromptSettings translation', () => {
      expect(enTranslations.PromptSettings).toBe('Prompt Settings');
    });

    it('should have AdvancedSettings translation', () => {
      expect(enTranslations.AdvancedSettings).toBe('Advanced Settings');
    });
  });

  describe('Translation completeness', () => {
    it('should have at least 50 translation keys', () => {
      const keys = Object.keys(enTranslations);
      expect(keys.length).toBeGreaterThanOrEqual(50);
    });

    it('should have all values as non-empty strings', () => {
      Object.values(enTranslations).forEach(value => {
        expect(typeof value).toBe('string');
        expect(value.length).toBeGreaterThan(0);
      });
    });

    it('should have unique translation values (excluding template strings)', () => {
      const values = Object.values(enTranslations);
      const nonTemplateValues = values.filter(value => !value.includes('{{'));
      const uniqueValues = [...new Set(nonTemplateValues)];
      
      // Allow some duplication but ensure most values are unique
      const duplicateCount = nonTemplateValues.length - uniqueValues.length;
      expect(duplicateCount).toBeLessThan(10); // Allow some common words like 'error', 'success', etc.
    });

    it('should have consistent template variable syntax', () => {
      const templateValues = Object.values(enTranslations).filter(value => value.includes('{{'));
      
      templateValues.forEach(value => {
        const templateMatches = value.match(/\{\{[^}]+\}\}/g);
        if (templateMatches) {
          templateMatches.forEach(match => {
            // Should be valid template variable format
            expect(match).toMatch(/^\{\{[a-zA-Z][a-zA-Z0-9]*\}\}$/);
          });
        }
      });
    });
  });

  describe('Specific key presence validation', () => {
    const requiredKeys = [
      'VideoSummary',
      'search',
      'cancel',
      'delete',
      'submit',
      'success',
      'error',
      'warning',
      'info'
    ];

    requiredKeys.forEach(key => {
      it(`should have required key: ${key}`, () => {
        expect(enTranslations).toHaveProperty(key);
        expect(typeof enTranslations[key as keyof typeof enTranslations]).toBe('string');
      });
    });
  });
});
