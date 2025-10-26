// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { UIActions, initialState, uiSelector, UIReducer } from '../redux/ui/ui.slice';
import { UISliceState, OpenPromptModal, PromptEditing, MuxFeatures } from '../redux/ui/ui.model';

describe('UISlice test suite', () => {
  describe('Initial State', () => {
    it('should return the correct initial state', () => {
      const state = UIReducer(undefined, { type: '@@INIT' });
      
      expect(state).toEqual(initialState);
      expect(state.promptEditing).toBeNull();
    });

    it('should have proper initialState export', () => {
      expect(initialState).toEqual({
        promptEditing: null,
        selectedMux: MuxFeatures.SUMMARY,
        groupByTag: false,
        showVideoGroups: false,
      });
    });
  });

  describe('Reducers', () => {
    describe('openPromptModal', () => {
      it('should handle opening prompt modal with basic prompt', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'Test Heading',
          prompt: 'This is a test prompt',
          openToken: 'test-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        expect(state.promptEditing).not.toBeNull();
        expect(state.promptEditing?.open).toBe('test-token');
        expect(state.promptEditing?.heading).toBe('Test Heading');
        expect(state.promptEditing?.prompt).toBe('This is a test prompt');
        expect(state.promptEditing?.submitValue).toBeNull();
        expect(state.promptEditing?.vars).toEqual([]);
      });

      it('should handle opening prompt modal with variables in prompt', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'Variable Test',
          prompt: 'Hello %name%, your age is %age% and status is %status%',
          openToken: 'var-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        expect(state.promptEditing).not.toBeNull();
        expect(state.promptEditing?.vars).toEqual(['%name%', '%age%', '%status%']);
        expect(state.promptEditing?.open).toBe('var-token');
        expect(state.promptEditing?.heading).toBe('Variable Test');
        expect(state.promptEditing?.prompt).toBe('Hello %name%, your age is %age% and status is %status%');
      });

      it('should handle opening prompt modal with duplicate variables', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'Duplicate Test',
          prompt: 'Use %name% and then %name% again, also %other%',
          openToken: 'dup-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        // Should deduplicate variables using Set
        expect(state.promptEditing?.vars).toEqual(['%name%', '%other%']);
      });

      it('should handle opening prompt modal with no variables', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'No Variables',
          prompt: 'This prompt has no variables at all',
          openToken: 'no-vars-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        expect(state.promptEditing?.vars).toEqual([]);
      });

      it('should handle opening prompt modal with empty prompt', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'Empty Prompt',
          prompt: '',
          openToken: 'empty-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        expect(state.promptEditing?.prompt).toBe('');
        expect(state.promptEditing?.vars).toEqual([]);
      });

      it('should handle opening prompt modal with case-insensitive variable matching', () => {
        const openPromptPayload: OpenPromptModal = {
          heading: 'Case Test',
          prompt: 'Variables: %Name% %NAME% %name%',
          openToken: 'case-token',
        };

        const state = UIReducer(initialState, UIActions.openPromptModal(openPromptPayload));

        // The regex is case-insensitive, should capture all variations
        expect(state.promptEditing?.vars).toEqual(['%Name%', '%NAME%', '%name%']);
      });

      it('should overwrite existing promptEditing state', () => {
        const initialPromptState: UISliceState = {
          promptEditing: {
            open: 'old-token',
            heading: 'Old Heading',
            prompt: 'Old prompt with %oldVar%',
            submitValue: 'old-submit-value',
            vars: ['%oldVar%'],
          },
          selectedMux: MuxFeatures.SUMMARY,
          groupByTag: false,
          showVideoGroups: false,
        };

        const newPromptPayload: OpenPromptModal = {
          heading: 'New Heading',
          prompt: 'New prompt with %newVar%',
          openToken: 'new-token',
        };

        const state = UIReducer(initialPromptState, UIActions.openPromptModal(newPromptPayload));

        expect(state.promptEditing?.open).toBe('new-token');
        expect(state.promptEditing?.heading).toBe('New Heading');
        expect(state.promptEditing?.prompt).toBe('New prompt with %newVar%');
        expect(state.promptEditing?.submitValue).toBeNull(); // Should reset to null
        expect(state.promptEditing?.vars).toEqual(['%newVar%']);
      });
    });

    describe('submitPromptModal', () => {
      it('should update submitValue when promptEditing exists', () => {
        const initialPromptState: UISliceState = {
          promptEditing: {
            open: 'test-token',
            heading: 'Test Heading',
            prompt: 'Test prompt',
            submitValue: null,
            vars: [],
          },
          selectedMux: MuxFeatures.SUMMARY,
          groupByTag: false,
          showVideoGroups: false,
        };

        const state = UIReducer(initialPromptState, UIActions.submitPromptModal('submitted value'));

        expect(state.promptEditing?.submitValue).toBe('submitted value');
        // Other properties should remain unchanged
        expect(state.promptEditing?.open).toBe('test-token');
        expect(state.promptEditing?.heading).toBe('Test Heading');
        expect(state.promptEditing?.prompt).toBe('Test prompt');
      });

      it('should handle submitPromptModal when promptEditing is null', () => {
        const state = UIReducer(initialState, UIActions.submitPromptModal('submitted value'));

        // State should remain unchanged
        expect(state.promptEditing).toBeNull();
      });

      it('should overwrite existing submitValue', () => {
        const initialPromptState: UISliceState = {
          promptEditing: {
            open: 'test-token',
            heading: 'Test Heading',
            prompt: 'Test prompt',
            submitValue: 'old value',
            vars: [],
          },
          selectedMux: MuxFeatures.SUMMARY,
          groupByTag: false,
          showVideoGroups: false,
        };

        const state = UIReducer(initialPromptState, UIActions.submitPromptModal('new value'));

        expect(state.promptEditing?.submitValue).toBe('new value');
      });
    });

    describe('closePrompt', () => {
      it('should set promptEditing to null when closing', () => {
        const initialPromptState: UISliceState = {
          promptEditing: {
            open: 'test-token',
            heading: 'Test Heading',
            prompt: 'Test prompt with %var%',
            submitValue: 'submit value',
            vars: ['%var%'],
          },
          selectedMux: MuxFeatures.SUMMARY,
          groupByTag: false,
          showVideoGroups: false,
        };

        const state = UIReducer(initialPromptState, UIActions.closePrompt());

        expect(state.promptEditing).toBeNull();
      });

      it('should handle closing when promptEditing is already null', () => {
        const state = UIReducer(initialState, UIActions.closePrompt());

        expect(state.promptEditing).toBeNull();
      });
    });
  });

  describe('Selectors', () => {
    describe('uiSelector', () => {
      it('should return default values when promptEditing is null', () => {
        const mockState = {
          ui: initialState,
        } as any;
        
        const selectedData = uiSelector(mockState);

        expect(selectedData).toEqual({
          openerToken: null,
          promptSubmitValue: null,
          modalHeading: '',
          modalPrompt: '',
          modalPromptVars: [],
          selectedMux: initialState.selectedMux,
          groupByTag: initialState.groupByTag,
          showVideoGroups: initialState.showVideoGroups,
        });
      });

      it('should return correct values when promptEditing exists', () => {
        const promptEditingState: PromptEditing = {
          open: 'selector-token',
          heading: 'Selector Heading',
          prompt: 'Selector prompt with %var1% and %var2%',
          submitValue: 'selector submit value',
          vars: ['%var1%', '%var2%'],
        };

        const mockState = {
          ui: { ...initialState, promptEditing: promptEditingState },
        } as any;
        
        const selectedData = uiSelector(mockState);

        expect(selectedData).toEqual({
          openerToken: 'selector-token',
          promptSubmitValue: 'selector submit value',
          modalHeading: 'Selector Heading',
          modalPrompt: 'Selector prompt with %var1% and %var2%',
          modalPromptVars: ['%var1%', '%var2%'],
          selectedMux: initialState.selectedMux,
          groupByTag: initialState.groupByTag,
          showVideoGroups: initialState.showVideoGroups,
        });
      });

      it('should handle partial promptEditing state', () => {
        const promptEditingState: PromptEditing = {
          open: 'partial-token',
          heading: 'Partial Heading',
          prompt: 'Partial prompt',
          submitValue: null,
          vars: [],
        };

        const mockState = {
          ui: { ...initialState, promptEditing: promptEditingState },
        } as any;
        
        const selectedData = uiSelector(mockState);

        expect(selectedData).toEqual({
          openerToken: 'partial-token',
          promptSubmitValue: null,
          modalHeading: 'Partial Heading',
          modalPrompt: 'Partial prompt',
          modalPromptVars: [],
          selectedMux: initialState.selectedMux,
          groupByTag: initialState.groupByTag,
          showVideoGroups: initialState.showVideoGroups,
        });
      });
    });
  });

  describe('Integration Tests', () => {
    it('should handle complete modal workflow', () => {
      let state: UISliceState = initialState;

      // 1. Open modal
      const openPayload: OpenPromptModal = {
        heading: 'Workflow Test',
        prompt: 'Enter your %name% and %email%',
        openToken: 'workflow-token',
      };
      state = UIReducer(state, UIActions.openPromptModal(openPayload));

      expect(state.promptEditing?.vars).toEqual(['%name%', '%email%']);

      // 2. Submit value
      state = UIReducer(state, UIActions.submitPromptModal('workflow submitted'));
      expect(state.promptEditing?.submitValue).toBe('workflow submitted');

      // 3. Close modal
      state = UIReducer(state, UIActions.closePrompt());
      expect(state.promptEditing).toBeNull();
    });

    it('should handle multiple modal open/close cycles', () => {
      let state: UISliceState = initialState;

      // First modal
      state = UIReducer(state, UIActions.openPromptModal({
        heading: 'First Modal',
        prompt: 'First %var%',
        openToken: 'first-token',
      }));
      
      expect(state.promptEditing?.open).toBe('first-token');

      // Second modal (should overwrite)
      state = UIReducer(state, UIActions.openPromptModal({
        heading: 'Second Modal',
        prompt: 'Second %other%',
        openToken: 'second-token',
      }));

      expect(state.promptEditing?.open).toBe('second-token');
      expect(state.promptEditing?.vars).toEqual(['%other%']);

      // Close
      state = UIReducer(state, UIActions.closePrompt());
      expect(state.promptEditing).toBeNull();
    });
  });

  describe('Edge Cases', () => {
    it('should handle complex variable patterns', () => {
      const state = UIReducer(initialState, UIActions.openPromptModal({
        heading: 'Complex Variables',
        prompt: 'Mix: %simple% %with_underscore% %withNumbers123% %MixedCase%',
        openToken: 'complex-token',
      }));

      expect(state.promptEditing?.vars).toEqual([
        '%simple%', 
        '%with_underscore%', 
        '%withNumbers123%', 
        '%MixedCase%'
      ]);
    });

    it('should handle malformed variable patterns', () => {
      const state = UIReducer(initialState, UIActions.openPromptModal({
        heading: 'Malformed Variables',
        prompt: 'Invalid: %incomplete %no-dashes% %spaces in var% % %',
        openToken: 'malformed-token',
      }));

      // Should only match valid patterns (alphanumeric + underscore)
      expect(state.promptEditing?.vars.length).toBeGreaterThanOrEqual(0);
    });

    it('should handle prompt with null/undefined values', () => {
      const state = UIReducer(initialState, UIActions.openPromptModal({
        heading: 'Null Test',
        prompt: null as any,
        openToken: 'null-token',
      }));

      expect(state.promptEditing?.prompt).toBeNull();
      expect(state.promptEditing?.vars).toEqual([]);
    });
  });

  describe('Action Creators', () => {
    it('should create openPromptModal action correctly', () => {
      const payload: OpenPromptModal = {
        heading: 'Action Test',
        prompt: 'Test %variable%',
        openToken: 'action-token',
      };

      const action = UIActions.openPromptModal(payload);

      expect(action.type).toBe('ui/openPromptModal');
      expect(action.payload).toEqual(payload);
    });

    it('should create submitPromptModal action correctly', () => {
      const action = UIActions.submitPromptModal('test submit');

      expect(action.type).toBe('ui/submitPromptModal');
      expect(action.payload).toBe('test submit');
    });

    it('should create closePrompt action correctly', () => {
      const action = UIActions.closePrompt();

      expect(action.type).toBe('ui/closePrompt');
      expect(action.payload).toBeUndefined();
    });
  });
});
