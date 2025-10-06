// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { 
  PromptEditing, 
  UISliceState, 
  OpenPromptModal,
  MuxFeatures
} from '../redux/ui/ui.model';

describe('UI Model Interfaces', () => {
  describe('PromptEditing interface', () => {
    it('should define correct structure for PromptEditing', () => {
      const promptEditing: PromptEditing = {
        open: 'modal-id-123',
        heading: 'Edit Prompt',
        prompt: 'Enter your search query here',
        submitValue: 'confirmed',
        vars: ['variable1', 'variable2', 'variable3'],
      };

      expect(promptEditing.open).toBe('modal-id-123');
      expect(promptEditing.heading).toBe('Edit Prompt');
      expect(promptEditing.prompt).toBe('Enter your search query here');
      expect(promptEditing.submitValue).toBe('confirmed');
      expect(promptEditing.vars).toEqual(['variable1', 'variable2', 'variable3']);
    });

    it('should allow submitValue to be null', () => {
      const promptEditing: PromptEditing = {
        open: 'modal-id-456',
        heading: 'Test Heading',
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      };

      expect(promptEditing.submitValue).toBeNull();
    });
  });

  describe('UISliceState interface', () => {
    it('should create UISliceState with valid promptEditing', () => {
      const promptEditing: PromptEditing = {
        open: 'state-test',
        heading: 'State Test',
        prompt: 'Test prompt',
        submitValue: 'test-submit',
        vars: ['testVar'],
      };

      const uiState: UISliceState = {
        promptEditing,
        selectedMux: MuxFeatures.SUMMARY,
        groupByTag: false,
        showVideoGroups: false,
      };
      
      expect(uiState.promptEditing).toBe(promptEditing);
      expect(uiState.promptEditing?.open).toBe('state-test');
      expect(uiState.promptEditing?.heading).toBe('State Test');
    });

    it('should allow promptEditing to be null', () => {
      const uiState: UISliceState = {
        promptEditing: null,
        selectedMux: MuxFeatures.SEARCH,
        groupByTag: false,
        showVideoGroups: false,
      };

      expect(uiState.promptEditing).toBeNull();
    });
  });

  describe('OpenPromptModal interface', () => {
    it('should define correct structure for OpenPromptModal', () => {
      const openPromptModal: OpenPromptModal = {
        heading: 'Open Prompt Modal',
        prompt: 'Please enter your input',
        openToken: 'token-abc-123',
      };

      expect(openPromptModal.heading).toBe('Open Prompt Modal');
      expect(openPromptModal.prompt).toBe('Please enter your input');
      expect(openPromptModal.openToken).toBe('token-abc-123');
    });
  });
});
