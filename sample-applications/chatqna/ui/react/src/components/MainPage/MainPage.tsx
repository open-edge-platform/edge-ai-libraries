// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState, type FC } from 'react';
import { Grid } from '@carbon/react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import ConversationSideBar from '../Conversation/ConversationSideBar.tsx';
import Conversation from '../Conversation/Conversation.tsx';
import Notice from '../Notice/Notice.tsx';
import Navbar from '../Navbar/Navbar.tsx';

const StyledGrid = styled(Grid)`
  display: grid;
  grid-template-columns: 15rem auto;
  grid-template-rows: 1fr;
  @media (min-width: 1700px) {
    grid-template-columns: 20rem auto;
  }
  @media (min-width: 2000px) {
    grid-template-columns: 25rem auto;
  }
  @media (min-width: 2300px) {
    grid-template-columns: 30rem auto;
  }
  padding-inline: 0;
  flex-grow: 1;
  max-inline-size: 100%;
`;

const StyledMain = styled.main`
  height: 100vh;
  display: flex;
  flex-direction: column;
`;

const HiddenButton = styled.button`
  display: none;
`;

const MainPage: FC = () => {
  const { t } = useTranslation();
  const message = <div>{t('noticeMessage')}</div>;
  const [isNoticeVisible, setIsNoticeVisible] = useState<boolean>(false);

  return (
    <StyledMain>
      <Navbar />
      <HiddenButton
        data-testid='toggle-notice'
        onClick={() => setIsNoticeVisible(true)}
      >
        {t('showNoticeHiddenButton')}
      </HiddenButton>

      <Notice
        message={message}
        isNoticeVisible={isNoticeVisible}
        setIsNoticeVisible={setIsNoticeVisible}
      />
      <StyledGrid>
        <ConversationSideBar />
        <Conversation />
      </StyledGrid>
    </StyledMain>
  );
};

export default MainPage;
