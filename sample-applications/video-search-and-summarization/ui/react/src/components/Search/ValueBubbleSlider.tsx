// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Slider } from '@carbon/react';
import { FC } from 'react';
import styled from 'styled-components';

// Leaves room for half a bubble at either end, so it stays inside the card
// when the thumb is at min or max.
const EDGE_ROOM = '1rem';

// Track centre = top padding + slider block padding (2.375rem); the bottom
// padding makes that also the centre of the whole block, so controls centred
// next to it line up with the track.
const Wrapper = styled.div`
  position: relative;
  padding: 1.75rem ${EDGE_ROOM} 0.75rem;

  /* Carbon puts the min/max labels beside the track; they are shown below it
     instead so the track spans the full width and the bubble lines up. */
  .cds--form-item {
    align-items: stretch;
  }
  .cds--slider-container {
    gap: 0;
    width: 100%;
  }
  /* The bubble replaces Carbon's hover-only value tooltip. */
  .cds--slider__thumb-wrapper .cds--popover {
    display: none;
  }
  .cds--slider__range-label {
    display: none;
  }
  .cds--slider {
    min-inline-size: 0;
    max-inline-size: none;
    padding-block: 0.625rem;
  }
`;

const BubbleTrack = styled.div`
  position: absolute;
  top: 0;
  left: ${EDGE_ROOM};
  right: ${EDGE_ROOM};
  height: 1.5rem;
  pointer-events: none;
`;

const Bubble = styled.output<{ $disabled: boolean }>`
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  background: ${({ $disabled }) => ($disabled ? '#c6c6c6' : '#393939')};
  color: ${({ $disabled }) => ($disabled ? '#525252' : '#ffffff')};
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1rem;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;

  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 0.25rem solid transparent;
    border-top-color: ${({ $disabled }) => ($disabled ? '#c6c6c6' : '#393939')};
  }
`;

const RangeLabels = styled.div`
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  line-height: 1rem;
  color: var(--cds-text-helper, #6f6f6f);
`;

export interface ValueBubbleSliderProps {
  id: string;
  labelText: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
  /**
   * Called once the user lets go: on mouse/touch release, or on key up after
   * moving the thumb with the keyboard. `onChange` fires on every step.
   */
  onRelease?: (value: number) => void;
  disabled?: boolean;
  format?: (value: number) => string;
}

// Keys Carbon's slider moves the thumb with.
const SLIDER_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);

/** Carbon slider with its current value always shown in a bubble above the thumb. */
export const ValueBubbleSlider: FC<ValueBubbleSliderProps> = ({
  id,
  labelText,
  min,
  max,
  step,
  value,
  onChange,
  onRelease,
  disabled = false,
  format = String,
}) => {
  const clamped = Math.min(max, Math.max(min, value));
  const percent = max > min ? ((clamped - min) / (max - min)) * 100 : 0;

  return (
    <Wrapper
      onKeyUp={(ev) => {
        if (onRelease && !disabled && SLIDER_KEYS.has(ev.key)) onRelease(value);
      }}
    >
      <BubbleTrack>
        <Bubble $disabled={disabled} htmlFor={id} data-testid={`${id}-bubble`} style={{ left: `${percent}%` }}>
          {format(clamped)}
        </Bubble>
      </BubbleTrack>
      <Slider
        id={id}
        labelText={labelText}
        hideLabel
        min={min}
        max={max}
        step={step}
        value={value}
        hideTextInput
        disabled={disabled}
        onChange={({ value: next }) => onChange(next)}
        onRelease={onRelease ? ({ value: next }) => !disabled && onRelease(next) : undefined}
      />
      <RangeLabels aria-hidden>
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </RangeLabels>
    </Wrapper>
  );
};

export default ValueBubbleSlider;
