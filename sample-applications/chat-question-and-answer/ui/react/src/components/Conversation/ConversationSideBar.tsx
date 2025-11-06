// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { ScrollAreaAutosize, Title, ActionIcon, TextInput, Loader } from "@mantine/core"
import { IconEdit, IconTrash, IconCheck, IconX } from "@tabler/icons-react"
import { useState } from "react"

import contextStyles from "../../styles/components/context.module.scss"
import { useAppDispatch, useAppSelector } from "../../redux/store"
import { conversationSelector, setSelectedConversationId, deleteConversation, updateConversationTitle } from "../../redux/Conversation/ConversationSlice"

export interface ConversationContextProps {
    title: string
}

export function ConversationSideBar({ title }: ConversationContextProps) {
    const { conversations, selectedConversationId, isGenerating } = useAppSelector(conversationSelector)
    const dispatch = useAppDispatch()
    const [editingId, setEditingId] = useState<string | null>(null)
    const [editingTitle, setEditingTitle] = useState("")
    const [originalTitle, setOriginalTitle] = useState("")
    const [hoveredId, setHoveredId] = useState<string | null>(null)

    const handleEditStart = (conversationId: string, currentTitle: string) => {
        setEditingId(conversationId)
        setEditingTitle(currentTitle)
        setOriginalTitle(currentTitle)
    }

    const handleEditSave = () => {
        if (editingId) {
            // Use original title if new title is empty/undefined, otherwise use trimmed new title
            const finalTitle = editingTitle.trim() || originalTitle
            dispatch(updateConversationTitle({ id: editingId, updatedTitle: finalTitle }))
        }
        setEditingId(null)
        setEditingTitle("")
        setOriginalTitle("")
    }

    const handleEditCancel = () => {
        setEditingId(null)
        setEditingTitle("")
        setOriginalTitle("")
    }

    const handleDelete = (conversationId: string) => {
        const confirmDelete = window.confirm(
            'Are you sure you want to delete this conversation? This action cannot be undone.'
        );
        if (!confirmDelete) {
            return;
        }
        dispatch(deleteConversation(conversationId))
    }

    const conversationList = conversations?.map((curr: any) => (
        <div
            className={contextStyles.contextListItem}
            data-active={selectedConversationId === curr.conversationId || undefined}
            onMouseEnter={() => setHoveredId(curr.conversationId)}
            onMouseLeave={() => setHoveredId(null)}
            onClick={(event: any) => {
                event.preventDefault()
                if (editingId !== curr.conversationId) {
                    dispatch(setSelectedConversationId(curr.conversationId))
                }
            }}
            key={curr.conversationId}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
        >
            {editingId === curr.conversationId ? (
                <div style={{ display: 'flex', alignItems: 'center', flex: 1, gap: '4px' }}>
                    <TextInput
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.currentTarget.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') handleEditSave()
                            if (e.key === 'Escape') handleEditCancel()
                        }}
                        size="xs"
                        style={{ flex: 1 }}
                        autoFocus
                    />
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="green"
                        onClick={(e) => {
                            e.stopPropagation()
                            handleEditSave()
                        }}
                    >
                        <IconCheck size={12} />
                    </ActionIcon>
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="red"
                        onClick={(e) => {
                            e.stopPropagation()
                            handleEditCancel()
                        }}
                    >
                        <IconX size={12} />
                    </ActionIcon>
                </div>
            ) : (
                <>
                    <div style={{ display: 'flex', alignItems: 'center', flex: 1, gap: '6px' }}>
                        <div className={contextStyles.contextItemName} title={curr.title || "Untitled"}>
                            {curr.title || "Untitled"}
                        </div>
                        {isGenerating[curr.conversationId] && (
                            <Loader size="xs" color="blue" />
                        )}
                    </div>
                    {hoveredId === curr.conversationId && (
                        <div style={{ display: 'flex', gap: '1px', marginLeft: '4px' }}>
                            <ActionIcon
                                size="sm"
                                variant="subtle"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    handleEditStart(curr.conversationId, curr.title || "Untitled")
                                }}
                                style={{ minWidth: '24px', height: '24px' }}
                            >
                                <IconEdit size={14} />
                            </ActionIcon>
                            <ActionIcon
                                size="sm"
                                variant="subtle"
                                color="red"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    handleDelete(curr.conversationId)
                                }}
                                style={{ minWidth: '24px', height: '24px' }}
                            >
                                <IconTrash size={14} />
                            </ActionIcon>
                        </div>
                    )}
                </>
            )}
        </div>
    ))

    return (
        <div className={contextStyles.contextWrapper}>
            <Title order={3} className={contextStyles.contextTitle}>
                {title}
            </Title>
            <div className={contextStyles.chatHistoryTitle}>
                Chat History
            </div>
            <ScrollAreaAutosize type="hover" scrollHideDelay={0}>
                <div className={contextStyles.contextList}>{conversationList}</div>
            </ScrollAreaAutosize>
        </div>
    )
}
