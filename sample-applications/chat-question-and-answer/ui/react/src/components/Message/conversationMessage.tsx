// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { DateTime } from "luxon"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

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

  const normalizedMessage = message.replace(/\\n/g, "\n")

  return (
    <div className={`${style.messageRow} ${human ? style.user : style.ai}`}>
      <div className={`${style.messageIcon} ${human ? style.userIcon : style.aiIcon}`}>
        {human ? "U" : "Q"}
      </div>

      <div className={style.messageContent}>
        <div className={`${style.bubble} ${human ? style.userBubble : style.aiBubble}`}>
          <div className={style.markdownContent}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {normalizedMessage}
            </ReactMarkdown>

            {showBlinkingIndicator && (
              <span
                className={conversationStyles.blinkingIndicator}
                style={{ marginLeft: "4px", display: "inline-block", verticalAlign: "baseline" }}
              />
            )}
          </div>

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