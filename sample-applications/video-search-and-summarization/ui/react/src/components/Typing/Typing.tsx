// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FC } from 'react';
import styled from 'styled-components';

interface TypingProps {
  text: string;
  speed?: number;
  children?: React.ReactNode;
}

const TypingWrapper = styled.div`
  display: flex;
  justify-content: flex-end;
`;

const TypingContainer = styled.div`
  width: 200px;
  white-space: pre-wrap;
  margin: 1rem 1rem 0 0;
`;

const Typing: FC<TypingProps> = ({ text, speed = 100, children }) => {
  const [displayedText, setDisplayedText] = useState<string>('');
  const [index, setIndex] = useState<number>(0);

  useEffect(() => {
    if (index < text.length) {
      const timeoutId = setTimeout(() => {
        setDisplayedText((prev) => prev + text[index]);
        setIndex((prev) => prev + 1);
      }, speed);

      return () => clearTimeout(timeoutId);
    }
  }, [index, text]);

  return (
    <TypingWrapper>
      <TypingContainer>
        <p>{displayedText}</p>
        {index >= text.length && children}
      </TypingContainer>
    </TypingWrapper>
  );
};

export default Typing;
