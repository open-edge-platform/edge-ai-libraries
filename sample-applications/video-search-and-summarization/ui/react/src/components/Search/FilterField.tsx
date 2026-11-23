// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Tooltip } from '@carbon/react';
import { Information, Return } from '@carbon/icons-react';
import { FC } from 'react';
import styled from 'styled-components';

export type InfoTooltipAlign = 'top' | 'top-start' | 'bottom' | 'bottom-start';

/**
 * Shared layout for the search filter controls, so every filter card has the
 * same title row, spacing and helper text. The fieldset is a flex column that
 * fills its card, and the helper text sits at the bottom, so cards of equal
 * height line their rows up.
 */
export const FilterFieldset = styled.fieldset<{ $maxWidth?: string }>`
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  gap: 0.5rem;
  border: none;
  margin: 0;
  padding: 0;
  min-inline-size: 0;
  width: 100%;
  max-width: ${({ $maxWidth }) => $maxWidth ?? 'none'};
`;

export const FilterLegend = styled.legend`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  width: 100%;
  min-height: 1.25rem;
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.29;
  color: var(--cds-text-primary, #161616);
`;

/** Pushes the rest of the title row (e.g. a toggle) to the right edge. */
export const FilterLegendEnd = styled.span`
  display: inline-flex;
  align-items: center;
  margin-left: auto;

  /* A toggle here is labelled by the title; drop Carbon's visible side text
     (it is aria-hidden, the accessible name comes from the label). */
  .cds--toggle__text {
    display: none;
  }
`;

/** Height of a ValueBubbleSlider, whose track sits at its vertical centre. */
export const FILTER_BODY_SLIDER_HEIGHT = '4.75rem';

/**
 * The control row, with its controls centred vertically. Cards side by side
 * give it the same min-height (FILTER_BODY_SLIDER_HEIGHT), so their inputs
 * and slider tracks share one centre line.
 */
export const FilterBody = styled.div`
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
`;

export const FilterHelp = styled.p`
  margin-top: auto;
  font-size: 0.75rem;
  line-height: 1.34;
  font-weight: 400;
  color: var(--cds-text-helper, #6f6f6f);
`;

const InfoButton = styled.button`
  display: inline-flex;
  align-items: center;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: inherit;
`;

export interface InfoTooltipProps {
  label: string;
  ariaLabel: string;
  align?: InfoTooltipAlign;
}

/** The (i) icon next to a filter title, explaining the filter on hover/focus. */
export const InfoTooltip: FC<InfoTooltipProps> = ({ label, ariaLabel, align = 'bottom-start' }) => (
  <Tooltip align={align} label={label}>
    <InfoButton type='button' aria-label={ariaLabel}>
      <Information size={16} />
    </InfoButton>
  </Tooltip>
);

const ApplyButton = styled.button<{ $pending: boolean }>`
  position: absolute;
  /* Centred on a small (2rem) input; top-anchored so an error message shown
     below the input does not move it. */
  top: 0.25rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  border: 0;
  border-radius: 0.25rem;
  background: ${({ $pending }) => ($pending ? 'var(--cds-button-primary, #0f62fe)' : 'transparent')};
  color: ${({ $pending }) => ($pending ? '#ffffff' : 'var(--cds-icon-secondary, #8d8d8d)')};
  cursor: ${({ $pending }) => ($pending ? 'pointer' : 'default')};
  transition:
    background 110ms,
    color 110ms;

  &:disabled {
    color: var(--cds-icon-disabled, #c6c6c6);
    background: transparent;
  }
`;

export interface ApplyIconButtonProps {
  /** True while the field shows a value that has not been applied yet. */
  pending: boolean;
  disabled?: boolean;
  /** Distance from the right edge of the positioned parent. */
  right?: string;
  pendingLabel: string;
  appliedLabel: string;
  testId?: string;
  onApply: () => void;
}

/**
 * The small Enter (↵) icon inside a filter's text box. Blue while the typed
 * value is still a draft (click to apply, same as pressing Enter), grey once
 * the value has been applied. Its parent must be `position: relative`.
 */
export const ApplyIconButton: FC<ApplyIconButtonProps> = ({
  pending,
  disabled = false,
  right = '0.25rem',
  pendingLabel,
  appliedLabel,
  testId,
  onApply,
}) => {
  const label = pending ? pendingLabel : appliedLabel;
  return (
    <ApplyButton
      type='button'
      // Enter / Tab already apply from the keyboard; this is for pointers.
      tabIndex={-1}
      $pending={pending}
      style={{ right }}
      data-state={pending ? 'pending' : 'applied'}
      data-testid={testId}
      aria-label={label}
      title={label}
      disabled={disabled}
      // Keep focus in the field, so the click applies rather than a blur first.
      onMouseDown={(ev) => ev.preventDefault()}
      onClick={onApply}
    >
      <Return size={16} />
    </ApplyButton>
  );
};
