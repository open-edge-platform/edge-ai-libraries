// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SyntheticEvent, useState, useEffect } from 'react'
import { Button, Drawer, FileInput, Text, TextInput, SegmentedControl,
  Table, Checkbox, Group, Stack, Paper, Badge, Divider} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconTrash, IconFile } from '@tabler/icons-react'
import { useAppDispatch, useAppSelector } from '../../redux/store'
import { submitDataSourceURL, uploadFile, fetchInitialFiles, fetchInitialLinks,
  removeFile, removeAllFiles, removeLink, removeAllLinks, 
  conversationSelector} from '../../redux/Conversation/ConversationSlice'
import { isValidUrl, extractOriginalFilename } from '../../utils/util'
import { MAX_FILE_SIZE } from '../../utils/constant'

type Props = {
  opened: boolean
  onClose: () => void
}

export default function DataSource({ opened, onClose }: Props) {
  const title = "Data Source"
  const [file, setFile] = useState<File | null>(null)
  const [uploadMethod, setUploadMethod] = useState<string>('file')
  const [url, setURL] = useState<string>("")
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [selectedLinks, setSelectedLinks] = useState<string[]>([])
  
  const dispatch = useAppDispatch()
  const { files, links, isUploading, isWaitingForFirstToken } = useAppSelector(conversationSelector)
  
  // Check if any conversation is currently waiting for first token
  const isAnyConversationWaitingForFirstToken = Object.values(isWaitingForFirstToken).some(Boolean)

  // Fetch initial data when component opens
  useEffect(() => {
    if (opened) {
      dispatch(fetchInitialFiles())
      dispatch(fetchInitialLinks())
    }
  }, [opened, dispatch])

  const handleFileUpload = async () => {
    if (!file) return;

    // Check file size (MAX_FILE_SIZE is in MB)
    const fileSizeInMB = file.size / (1024 * 1024);
    if (fileSizeInMB > MAX_FILE_SIZE) {
      notifications.show({
        id: 'file-size-error',
        title: 'File Size Exceeded',
        message: `File size exceeds ${MAX_FILE_SIZE} MB limit. Current size: ${fileSizeInMB.toFixed(2)} MB`,
        color: 'red',
        autoClose: 3000,
      });
      setFile(null); // Clear the selected file
      return;
    }

    // Check for duplicate by comparing original filename
    const originalFileName = file.name;
    const isDuplicate = files.some((existingFile: any) => {
      const existingOriginalName = extractOriginalFilename(existingFile.file_name);
      return existingOriginalName === originalFileName;
    });

    if (isDuplicate) {
      notifications.show({
        id: 'duplicate-file',
        title: 'File Already Exists',
        message: `A file with the name "${originalFileName}" already exists. Please choose a different file.`,
        color: 'red',
        autoClose: 3000,
      });
      setFile(null); // Clear the selected file
      return;
    }

    try {
      await dispatch(uploadFile({ file })).unwrap();
      setFile(null);
      dispatch(fetchInitialFiles()); // Refresh files list
      onClose(); // Close drawer on success
    } catch (error) {
      console.error('Failed to upload file:', error);
    }
  }

  const handleURLSubmit = async () => {
    if (url) {
      const inputLinks = url.split(";")
        .map((link: string) => link.trim())
        .filter(Boolean)
    
      const validLinks = inputLinks.filter((link: string) => isValidUrl(link))

      if (validLinks.length === 0) {
        alert('Please enter valid HTTP or HTTPS URLs')
        return
      }

      if (validLinks.length !== inputLinks.length) {
        const invalidLinks = inputLinks.filter((link: string) => !isValidUrl(link))
        alert(`Warning: ${invalidLinks.length} invalid URL(s) were filtered out: ${invalidLinks.join(', ')}`)
      }

      // Check for duplicate URLs against existing database links
      const duplicateLinks = validLinks.filter((newLink: string) =>
        links.some((existingLink: any) => existingLink === newLink)
      );

      if (duplicateLinks.length > 0) {
        const confirmUpload = window.confirm(
          `The following URL(s) already exist:\n${duplicateLinks.join('\n')}\n\nDo you want to submit anyway?`
        );
        if (!confirmUpload) {
          return;
        }
      }

      try {
        await dispatch(submitDataSourceURL({ link_list: validLinks })).unwrap()
        console.log('URLs submitted successfully')
        setURL('')
        dispatch(fetchInitialLinks()) // Refresh links list
        
        // Small delay to ensure notification is visible before closing drawer
        setTimeout(() => {
          onClose() // Close drawer on success
        }, 500)
      } catch (error) {
        console.error('Failed to submit URLs:', error)
        // Don't close drawer on error so user can try again
      }
    }
  }

  const handleChange = (event: SyntheticEvent) => {
    setURL((event.currentTarget as HTMLInputElement).value)
  }

    const handleSelectFile = (fileName: string, isSelected: boolean) => {
    if (isSelected) {
      setSelectedFiles((prev: string[]) => [...prev, fileName])
    } else {
      setSelectedFiles((prev: string[]) => prev.filter((name: string) => name !== fileName))
    }
  }

  const handleDeleteSelectedFiles = async () => {
    if (selectedFiles.length === 0) return

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ${selectedFiles.length} selected file(s)? This action cannot be undone.`
    );
    if (!confirmDelete) {
      return;
    }

    try {
      for (const fileName of selectedFiles) {
        const file = files.find((f: any) => f.file_name === fileName)
        if (file) {
          await dispatch(removeFile({
            fileName,
            bucketName: file.bucket_name
          })).unwrap()
        }
      }
      setSelectedFiles([])
      dispatch(fetchInitialFiles())
    } catch (error) {
      console.error('Failed to delete files:', error)
    }
  }

  const handleDeleteAllFiles = async () => {
    if (files.length === 0) return

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ALL file(s)? This action cannot be undone.`
    );
    if (!confirmDelete) {
      return;
    }

    try {
      const bucketName = files[0]?.bucket_name || 'default'
      await dispatch(removeAllFiles({ bucketName })).unwrap()
      setSelectedFiles([])
      dispatch(fetchInitialFiles())
    } catch (error) {
      console.error('Failed to delete all files:', error)
    }
  }

    const handleSelectLink = (link: string, isSelected: boolean) => {
    if (isSelected) {
      setSelectedLinks((prev: string[]) => [...prev, link])
    } else {
      setSelectedLinks((prev: string[]) => prev.filter((l: string) => l !== link))
    }
  }

  const handleDeleteSelectedLinks = async () => {
    if (selectedLinks.length === 0) return

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ${selectedLinks.length} selected URL(s)? This action cannot be undone.`
    );
    if (!confirmDelete) {
      return;
    }

    try {
      for (const linkName of selectedLinks) {
        await dispatch(removeLink({ linkName })).unwrap()
      }
      setSelectedLinks([])
      dispatch(fetchInitialLinks())
    } catch (error) {
      console.error('Failed to delete links:', error)
    }
  }

  const handleDeleteAllLinks = async () => {
    if (links.length === 0) return

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ALL URL(s)? This action cannot be undone.`
    );
    if (!confirmDelete) {
      return;
    }

    try {
      await dispatch(removeAllLinks({})).unwrap()
      setSelectedLinks([])
      dispatch(fetchInitialLinks())
    } catch (error) {
      console.error('Failed to delete all links:', error)
    }
  }

  return (
    <Drawer title={title} position="right" opened={opened} onClose={onClose} withOverlay={false} size="xl">
      <Stack gap="md">
        <Text size="sm">
          Please upload your local file or paste a remote file link, and Chat will respond based on the content of the uploaded file.
        </Text>

        {/* Upload Method Selection */}
        <Group justify="center">
          <SegmentedControl
            value={uploadMethod}
            onChange={setUploadMethod}
            data={[
              { label: 'Upload File', value: 'file' },
              { label: 'Use Link', value: 'url' }
            ]}
            size="sm"
          />
        </Group>

        {/* Upload Section */}
        {uploadMethod === 'file' ? (
            <Stack gap="sm">
              <FileInput 
                value={file} 
                onChange={setFile}
                placeholder="Choose File" 
                description="Choose a file to upload for RAG"
                accept=".pdf,.txt,.docx"
              />
              <Button 
                onClick={handleFileUpload} 
                disabled={!file || isUploading || isAnyConversationWaitingForFirstToken}
                size="sm"
                loading={isUploading}
              >
                Upload File
              </Button>
              {(isUploading || isAnyConversationWaitingForFirstToken) && (
                <Text size="xs" c="dimmed" ta="center">
                  {isUploading ? "Upload in progress..." : "System busy preparing response – upload available shortly"}
                </Text>
              )}
            </Stack>
          ) : (
            <Stack gap="sm">
              <TextInput 
                value={url} 
                onChange={handleChange} 
                placeholder='https://example.com' 
                description="Use semicolons (;) to separate multiple URLs"
              />
              <Button 
                onClick={handleURLSubmit} 
                disabled={!url || isUploading || isAnyConversationWaitingForFirstToken}
                size="sm"
                loading={isUploading}
              >
                Submit URLs
              </Button>
              {(isUploading || isAnyConversationWaitingForFirstToken) && (
                <Text size="xs" c="dimmed" ta="center">
                  {isUploading ? "Upload in progress..." : "System busy preparing response – upload available shortly"}
                </Text>
              )}
            </Stack>
          )}

        <Divider />

        {/* Files Management Section */}
        {uploadMethod === 'file' && files.length === 0 && (
          <Paper p="md" withBorder>
            <Text ta="center" c="dimmed" size="sm">
              Currently there are no files in the database. Please upload a file to get started.
            </Text>
          </Paper>
        )}

        {uploadMethod === 'file' && files.length > 0 && (
          <Paper p="md" withBorder>
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={500} size="md">Uploaded Files ({files.length})</Text>
                <Group gap="xs">
                  <Button
                    variant="outline"
                    color="red"
                    size="xs"
                    onClick={handleDeleteSelectedFiles}
                    disabled={selectedFiles.length === 0}
                    leftSection={<IconTrash size={14} />}
                  >
                    Delete Selected ({selectedFiles.length})
                  </Button>
                  <Button
                    variant="filled"
                    color="red"
                    size="xs"
                    onClick={handleDeleteAllFiles}
                    leftSection={<IconTrash size={14} />}
                  >
                    Delete All
                  </Button>
                </Group>
              </Group>

              <Table striped highlightOnHover withTableBorder>
                <thead>
                  <tr>
                    <th>Select</th>
                    <th>File Name</th>
                    <th>Bucket</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file: any) => (
                    <tr key={file.file_name}>
                      <td style={{ display: 'flex', justifyContent: 'center' }}>
                        <Checkbox
                          checked={selectedFiles.includes(file.file_name)}
                          onChange={(event: any) => handleSelectFile(file.file_name, event.currentTarget.checked)}
                        />
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <Group gap="xs" justify="center">
                          <IconFile size={16} />
                          <Text size="sm">{extractOriginalFilename(file.file_name)}</Text>
                        </Group>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <Badge variant="light" size="sm">{file.bucket_name}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Stack>
          </Paper>
        )}

        {/* Links Management Section */}
        {uploadMethod === 'url' && links.length === 0 && (
          <Paper p="md" withBorder>
            <Text ta="center" c="dimmed" size="sm">
              Currently there are no urls in the database. Please submit a url to get started.
            </Text>
          </Paper>
        )}

        {uploadMethod === 'url' && links.length > 0 && (
          <Paper p="md" withBorder>
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={500} size="md">Submitted URLs ({links.length})</Text>
                <Group gap="xs">
                  <Button
                    variant="outline"
                    color="red"
                    size="xs"
                    onClick={handleDeleteSelectedLinks}
                    disabled={selectedLinks.length === 0}
                    leftSection={<IconTrash size={14} />}
                  >
                    Delete Selected ({selectedLinks.length})
                  </Button>
                  <Button
                    variant="filled"
                    color="red"
                    size="xs"
                    onClick={handleDeleteAllLinks}
                    leftSection={<IconTrash size={14} />}
                  >
                    Delete All
                  </Button>
                </Group>
              </Group>

              <Table striped highlightOnHover withTableBorder>
                <thead>
                  <tr>
                    <th>Select</th>
                    <th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((link: any, index: number) => (
                    <tr key={index}>
                      <td style={{ display: 'flex', justifyContent: 'center' }}>
                        <Checkbox
                          checked={selectedLinks.includes(link)}
                          onChange={(event: any) => handleSelectLink(link, event.currentTarget.checked)}
                        />
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <Text size="sm" truncate="end">
                          {link}
                        </Text>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Stack>
          </Paper>
        )}
      </Stack>
    </Drawer>
  )
}
