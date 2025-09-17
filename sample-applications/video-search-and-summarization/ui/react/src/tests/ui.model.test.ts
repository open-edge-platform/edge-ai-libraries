// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect } from 'vitest';
import type { 
  PromptEditing, 
  UISliceState, 
  OpenPromptModal 
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

    it('should handle empty arrays for vars', () => {
      const promptEditing: PromptEditing = {
        open: 'test-open',
        heading: 'Test',
        prompt: 'Test prompt',
        submitValue: 'test-value',
        vars: [],
      };

      expect(promptEditing.vars).toEqual([]);
      expect(promptEditing.vars.length).toBe(0);
    });

    it('should handle multiple variables in vars array', () => {
      const variables = ['var1', 'var2', 'var3', 'var4', 'var5'];
      const promptEditing: PromptEditing = {
        open: 'multi-vars',
        heading: 'Multiple Variables',
        prompt: 'Prompt with multiple variables',
        submitValue: 'submit',
        vars: variables,
      };

      expect(promptEditing.vars.length).toBe(5);
      expect(promptEditing.vars).toEqual(variables);
    });

    it('should handle empty strings', () => {
      const promptEditing: PromptEditing = {
        open: '',
        heading: '',
        prompt: '',
        submitValue: '',
        vars: [''],
      };

      expect(promptEditing.open).toBe('');
      expect(promptEditing.heading).toBe('');
      expect(promptEditing.prompt).toBe('');
      expect(promptEditing.submitValue).toBe('');
      expect(promptEditing.vars).toEqual(['']);
    });
  });

  describe('UISliceState interface', () => {
    it('should define correct structure for UISliceState', () => {
      const promptEditing: PromptEditing = {
        open: 'state-test',
        heading: 'State Test',
        prompt: 'Testing state',
        submitValue: 'test-submit',
        vars: ['testVar'],
      };

      const uiState: UISliceState = {
        promptEditing: promptEditing,
      };

      expect(uiState.promptEditing).toBe(promptEditing);
      expect(uiState.promptEditing?.open).toBe('state-test');
      expect(uiState.promptEditing?.heading).toBe('State Test');
    });

    it('should allow promptEditing to be null', () => {
      const uiState: UISliceState = {
        promptEditing: null,
      };

      expect(uiState.promptEditing).toBeNull();
    });

    it('should maintain reference integrity', () => {
      const promptEditing: PromptEditing = {
        open: 'reference-test',
        heading: 'Reference Test',
        prompt: 'Testing reference',
        submitValue: null,
        vars: ['ref1', 'ref2'],
      };

      const uiState: UISliceState = {
        promptEditing: promptEditing,
      };

      // Modifying the original should reflect in the state
      promptEditing.open = 'modified-reference';
      expect(uiState.promptEditing?.open).toBe('modified-reference');
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

    it('should handle empty strings', () => {
      const openPromptModal: OpenPromptModal = {
        heading: '',
        prompt: '',
        openToken: '',
      };

      expect(openPromptModal.heading).toBe('');
      expect(openPromptModal.prompt).toBe('');
      expect(openPromptModal.openToken).toBe('');
    });

    it('should handle long strings', () => {
      const longHeading = 'This is a very long heading that could be used in a modal dialog to test if the interface handles lengthy text content properly';
      const longPrompt = 'This is an extremely long prompt text that might be used to describe complex instructions or detailed information that needs to be displayed in a modal';
      const longToken = 'very-long-token-string-that-could-be-generated-by-uuid-or-similar-mechanism-for-unique-identification';

      const openPromptModal: OpenPromptModal = {
        heading: longHeading,
        prompt: longPrompt,
        openToken: longToken,
      };

      expect(openPromptModal.heading.length).toBeGreaterThan(100);
      expect(openPromptModal.prompt.length).toBeGreaterThan(100);
      expect(openPromptModal.openToken.length).toBeGreaterThan(50);
    });
  });

  describe('Interface relationships and compatibility', () => {
    it('should ensure PromptEditing and OpenPromptModal share common fields', () => {
      const promptEditing: PromptEditing = {
        open: 'shared-test',
        heading: 'Shared Heading',
        prompt: 'Shared Prompt',
        submitValue: null,
        vars: [],
      };

      const openPromptModal: OpenPromptModal = {
        heading: promptEditing.heading,
        prompt: promptEditing.prompt,
        openToken: 'modal-token',
      };

      expect(openPromptModal.heading).toBe(promptEditing.heading);
      expect(openPromptModal.prompt).toBe(promptEditing.prompt);
    });

    it('should handle complex nesting scenarios', () => {
      const complexPromptEditing: PromptEditing = {
        open: 'complex-scenario',
        heading: 'Complex Scenario Test',
        prompt: 'This is a complex prompt with {var1} and {var2}',
        submitValue: 'complex-submit',
        vars: ['var1', 'var2', 'additionalVar'],
      };

      const complexUIState: UISliceState = {
        promptEditing: complexPromptEditing,
      };

      expect(complexUIState.promptEditing?.vars.length).toBe(3);
      expect(complexUIState.promptEditing?.prompt).toContain('{var1}');
      expect(complexUIState.promptEditing?.prompt).toContain('{var2}');
    });

    it('should verify type safety for all nullable fields', () => {
      // Test with null promptEditing
      const nullUIState: UISliceState = { promptEditing: null };
      expect(nullUIState.promptEditing).toBeNull();

      // Test with null submitValue
      const promptWithNullSubmit: PromptEditing = {
        open: 'null-submit-test',
        heading: 'Null Submit Test',
        prompt: 'Testing null submit',
        submitValue: null,
        vars: ['test'],
      };
      expect(promptWithNullSubmit.submitValue).toBeNull();
    });
  });
});
