// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import styled from 'styled-components';

export const FileLinkManagerWrapper = styled.div``;

export const Container = styled.div`
  overflow-y: auto;
`;

export const StyledButtonSet = styled.div`
  display: flex;
  justify-content: space-between;
`;

export const Button = styled.button`
  background-color: var(--color-button);
  color: white;
  border: none;
  padding: 5px 10px;
  cursor: pointer;

  &:disabled {
    background-color: var(--color-default);
    color: var(--color-disabled);
    cursor: not-allowed;
  }
`;

export const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
`;

export const TableHead = styled.thead`
  background-color: var(--color-table-head);
`;

export const TableRow = styled.tr`
  &:nth-child(even) {
    background-color: var (--color-table-row);
  }
`;

export const TableHeader = styled.th`
  padding: 10px;
  border: 1px solid var(--color-gray-4);
  text-align: left;
`;

export const TableBody = styled.tbody``;

export const TableCell = styled.td`
  padding: 10px;
  border: 1px solid var(--color-gray-4);
  word-break: break-word;
  line-height: 1.4;
`;

export const Checkbox = styled.input.attrs({ type: 'checkbox' })`
  margin: 0;
`;

export const StyledList = styled.ul`
  list-style-type: disc;
  padding-left: 3rem;
  margin: 0.5rem 0;
  word-break: break-word;

  & li {
    padding-bottom: 0.5rem;
  }
`;

export const ScrollableContainer = styled.div<{ $showField: boolean }>`
  overflow-y: auto;
  max-height: ${({ $showField }) =>
    $showField ? 'max(15vh, 150px)' : 'max(55vh, 475px)'};
`;

export const Strong = styled.p`
  font-weight: 500;
  margin-bottom: 0.5rem;
`;
