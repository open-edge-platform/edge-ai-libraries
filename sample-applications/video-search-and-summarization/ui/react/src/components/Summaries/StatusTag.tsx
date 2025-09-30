// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { CountStatus, StateActionStatus } from '../../redux/summary/summary';
import { useTranslation } from 'react-i18next';
import { Tag, Tooltip } from '@carbon/react';
import styled from 'styled-components';

export interface StatusTagProps {
  label: string;
  action?: StateActionStatus;
  count?: number;
  total?: number;
  size?: any;
}

export interface CountStatusEmpProps {
  status: CountStatus;
  label: string;
  // emphasis?: StateActionStatus;
}

const CicleStatusIndicator = styled.div`
  @keyframes fadeInOut {
    0% {
      opacity: 0.2;
    }
    50% {
      opacity: 1;
    }
    100% {
      opacity: 0.2;
    }
  }

  &.gray {
    background-color: var(--color-default);
  }
  &.purple {
    background-color: var(--color-warning);
  }

  &.blue {
    background-color: var(--color-info);
    animation: fadeInOut 2s;
    animation-iteration-count: infinite;
  }
  &.green {
    background-color: var(--color-success);
  }

  width: 1rem;
  height: 1rem;
  border-radius: 1rem;
  margin-left: 0.5rem;
`;

const statusPriority: StateActionStatus[] = [
  StateActionStatus.IN_PROGRESS,
  StateActionStatus.COMPLETE,
  StateActionStatus.READY,
  StateActionStatus.NA,
];

export const getStatusByPriority = (counts: CountStatus): StateActionStatus => {
  let currentStatus = StateActionStatus.NA;

  for (const status of statusPriority) {
    if (counts[status] > 0) {
      currentStatus = status;
    }
  }

  return currentStatus;
};

export const statusClassName = {
  [StateActionStatus.NA]: 'gray',
  [StateActionStatus.READY]: 'purple',
  [StateActionStatus.IN_PROGRESS]: 'blue',
  [StateActionStatus.COMPLETE]: 'green',
};

export const statusClassLabel = {
  [StateActionStatus.NA]: 'naTag',
  [StateActionStatus.READY]: 'readyTag',
  [StateActionStatus.IN_PROGRESS]: 'progressTag',
  [StateActionStatus.COMPLETE]: 'completeTag',
};

export const CountStatusEmp: FC<CountStatusEmpProps> = ({ status }) => {
  const { t } = useTranslation();

  return (
    <>
      {status[StateActionStatus.NA] > 0 && (
        <Tag size='md' type={statusClassName[StateActionStatus.NA] as any}>
          {t(statusClassLabel[StateActionStatus.NA])}: {status[StateActionStatus.NA]}
        </Tag>
      )}
      {status[StateActionStatus.READY] > 0 && (
        <Tag size='md' type={statusClassName[StateActionStatus.READY] as any}>
          {t(statusClassLabel[StateActionStatus.READY])}: {status[StateActionStatus.READY]}
        </Tag>
      )}
      {status[StateActionStatus.IN_PROGRESS] > 0 && (
        <Tag size='md' type={statusClassName[StateActionStatus.IN_PROGRESS] as any}>
          {t(statusClassLabel[StateActionStatus.IN_PROGRESS])}: {status[StateActionStatus.IN_PROGRESS]}
        </Tag>
      )}
      {status[StateActionStatus.COMPLETE] > 0 && (
        <Tag size='md' type={statusClassName[StateActionStatus.COMPLETE] as any}>
          {t(statusClassLabel[StateActionStatus.COMPLETE])}: {status[StateActionStatus.COMPLETE]}
        </Tag>
      )}
    </>
  );
};

export const StatusTag: FC<StatusTagProps> = ({ label, action, count, total }) => {
  const { t } = useTranslation();

  const trailingCount = (count?: number, total?: number) => {
    let order: string = '';

    if (count || total) {
      order = '(';

      if (count) {
        order += count;

        if (total) {
          order += `/${total}`;
        }
      }

      return order + `)`;
    }
  };

  return (
    <>
      {action && (
        <Tag size='md' title={label + ':' + t(statusClassLabel[action])} type={statusClassName[action] as any}>
          {label}: {t(statusClassLabel[action])} {trailingCount(count, total)}
        </Tag>
      )}
    </>
  );
};

export const StatusIndicator: FC<StatusTagProps> = ({ label, action }) => {
  return (
    <>
      <Tooltip label={label} autoAlign>
        <CicleStatusIndicator className={statusClassName[action ?? StateActionStatus.NA]}></CicleStatusIndicator>
      </Tooltip>
    </>
  );
};

export default StatusTag;
