// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { IconAi, IconUser } from "@tabler/icons-react"
import style from "./conversationMessage.module.scss"
import conversationStyles from "../../styles/components/conversation.module.scss"
import { Group, Text } from "@mantine/core"
import { DateTime } from "luxon"

export interface ConversationMessageProps {
  message: string
  human: boolean
  date: number
  showBlinkingIndicator?: boolean
}

export function ConversationMessage({ human, message, date, showBlinkingIndicator = false }: ConversationMessageProps) {
  const dateFormat = () => {
    return DateTime.fromJSDate(new Date(date)).toLocaleString(DateTime.DATETIME_MED)
  }

  return (
    <div className={style.conversationMessage}>
      <Group>
        {human && <IconUser />}
        {!human && <IconAi />}

        <div>
          <Text size="sm">
            {human && "You"} {!human && "Assistant"}
          </Text>
          <Text size="xs" c="dimmed">
            {dateFormat()}
          </Text>
        </div>
      </Group>
      <div style={{ paddingLeft: 54, paddingTop: 'var(--mantine-spacing-sm)' }}>
        <Text size="sm" component="span">
          {message}
        </Text>
        {showBlinkingIndicator && (
          <span
            className={conversationStyles.blinkingIndicator}
            style={{ marginLeft: '4px', display: 'inline-block', verticalAlign: 'baseline' }}
          />
        )}
      </div>
    </div>
  )
}
