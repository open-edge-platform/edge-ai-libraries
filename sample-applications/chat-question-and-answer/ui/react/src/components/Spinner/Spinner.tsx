// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { FC } from 'react';
import styled, { keyframes } from 'styled-components';

interface SpinnerProps {
  size?: number;
}

const stretchDelay = keyframes`
  0%, 40%, 100% {
    transform: scaleY(0.4);
  }
  20% {
    transform: scaleY(1);
  }
`;

const SpinnerContainer = styled.div<{ size: number }>`
  margin: 1rem auto 0;
  display: flex;
  justify-content: space-between;
  width: ${({ size }) => size}px;
  height: ${({ size }) => size}px;
`;

const Bar = styled.div<{ delay: string }>`
  background-color: var(--color-info);
  height: 100%;
  width: 2px;
  display: inline-block;
  animation: ${stretchDelay} 1.2s infinite ease-in-out;
  animation-delay: ${({ delay }) => delay};
`;

const Spinner: FC<SpinnerProps> = ({ size = 50 }) => {
  return (
    <SpinnerContainer data-testid='spinner-container' size={size}>
      <Bar delay='-1.2s' data-testid='spinner-bar' />
      <Bar delay='-1.1s' data-testid='spinner-bar' />
      <Bar delay='-1s' data-testid='spinner-bar' />
      <Bar delay='-0.9s' data-testid='spinner-bar' />
      <Bar delay='-0.8s' data-testid='spinner-bar' />
    </SpinnerContainer>
  );
};

export default Spinner;
