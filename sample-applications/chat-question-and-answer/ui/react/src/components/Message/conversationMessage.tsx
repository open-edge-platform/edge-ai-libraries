// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Text } from "@mantine/core"
import { DateTime } from "luxon"

import style from "./conversationMessage.module.scss"
import conversationStyles from "../../styles/components/conversation.module.scss"

export interface ConversationMessageProps {
  message: string
  human: boolean
  date: number
  showBlinkingIndicator?: boolean
  responseTimeMs?: number
}

export function ConversationMessage({
  human,
  message,
  date,
  showBlinkingIndicator = false,
  responseTimeMs,
}: ConversationMessageProps) {
  const dateFormat = () => {
    return DateTime.fromJSDate(new Date(date)).toLocaleString(DateTime.DATETIME_MED)
  }

  return (
    <div className={`${style.messageRow} ${human ? style.user : style.ai}`}>
      <div className={`${style.messageIcon} ${human ? style.userIcon : style.aiIcon}`}>
        {human ? "U" : "Q"}
      </div>

      <div className={style.messageContent}>
        <div className={`${style.bubble} ${human ? style.userBubble : style.aiBubble}`}>
          <Text size="sm" component="span">
            {message}
          </Text>

          {showBlinkingIndicator && (
            <span
              className={conversationStyles.blinkingIndicator}
              style={{ marginLeft: "4px", display: "inline-block", verticalAlign: "baseline" }}
            />
          )}
        </div>

        <div className={style.messageDate}>{dateFormat()}</div>

        {!human && responseTimeMs !== undefined && (
          <div className={style.responseTime}>
            <span className={style.responseDot} />
            <span className={style.responseValue}>
              {(responseTimeMs / 1000).toFixed(2)}s
            </span>
            <span className={style.responseLabel}>response time</span>
          </div>
        )}
      </div>
    </div>
  )
}