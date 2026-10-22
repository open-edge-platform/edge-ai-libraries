// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { IntersectionMarker } from './intersectionMarkers';

export interface IntersectionCardProps {
  marker: IntersectionMarker;
  /** Anchor point the card tail points at, in container-relative CSS pixels. */
  left: number;
  top: number;
  horizontalOffset?: number;
  placement?: 'above' | 'below';
  isActive: boolean;
  onActivate: (id: string) => void;
}

const CardAnchor = styled.div<{ $left: number; $top: number; $zIndex: number }>`
  position: absolute;
  left: ${({ $left }) => $left}px;
  top: ${({ $top }) => $top}px;
  z-index: ${({ $zIndex }) => $zIndex};
  touch-action: none;
`;

const CardShell = styled.div<{ $horizontalOffset: number; $placement: 'above' | 'below' }>`
  position: absolute;
  width: 10rem;
  transform: ${({ $horizontalOffset, $placement }) =>
    `translate(calc(-50% + ${$horizontalOffset}px), ${$placement === 'above' ? 'calc(-100% - 0.5rem)' : '0.5rem'})`};
`;

const CardBody = styled.div<{ $active: boolean }>`
  position: relative;
  width: 100%;
  border-radius: 0.375rem;
  overflow: hidden;
  background: #ffffff;
  box-shadow: ${({ $active }) => ($active ? '0 4px 16px rgba(0, 0, 0, 0.35)' : '0 2px 8px rgba(0, 0, 0, 0.25)')};
  border: 2px solid ${({ $active }) => ($active ? '#0f62fe' : 'rgba(0, 0, 0, 0.15)')};
  padding: 0.375rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const CardTail = styled.span<{ $horizontalOffset: number; $placement: 'above' | 'below' }>`
  position: absolute;
  left: ${({ $horizontalOffset }) => `calc(50% - ${$horizontalOffset}px)`};
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 0.5rem solid transparent;
  border-right: 0.5rem solid transparent;
  ${({ $placement }) =>
    $placement === 'above'
      ? 'top: 100%; border-top: 0.5rem solid #ffffff;'
      : 'bottom: 100%; border-bottom: 0.5rem solid #ffffff;'}
`;

const IntersectionLabel = styled.span`
  font-size: 0.75rem;
  font-weight: 600;
  color: #161616;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const CountBadge = styled.span`
  align-self: flex-start;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #ffffff;
  background: #0f62fe;
  padding: 0.0625rem 0.375rem;
  border-radius: 0.75rem;
`;

export const IntersectionCard: FC<IntersectionCardProps> = ({
  marker,
  left,
  top,
  horizontalOffset = 0,
  placement = 'above',
  isActive,
  onActivate,
}) => {
  const { t } = useTranslation();

  return (
    <CardAnchor
      $left={left}
      $top={top}
      $zIndex={isActive ? 100000 : Math.round((90 - marker.lat) * 10) + 1}
      onMouseEnter={() => onActivate(marker.id)}
      data-testid={`intersection-card-${marker.id}`}
    >
      <CardShell $horizontalOffset={horizontalOffset} $placement={placement}>
        <CardBody $active={isActive}>
          <IntersectionLabel title={marker.label}>{marker.label}</IntersectionLabel>
          <CountBadge>{t('IntersectionClipCount', { count: marker.resultIndices.length })}</CountBadge>
        </CardBody>
        <CardTail $horizontalOffset={horizontalOffset} $placement={placement} aria-hidden='true' />
      </CardShell>
    </CardAnchor>
  );
};

export default IntersectionCard;
