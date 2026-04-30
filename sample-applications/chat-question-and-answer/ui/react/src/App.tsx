// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./App.scss"
import { MantineProvider } from "@mantine/core"
import '@mantine/notifications/styles.css';
import Conversation from "./components/Conversation/Conversation"
import { Notifications } from '@mantine/notifications';
import { Navbar } from "./components/Navbar/Navbar";

const title = "ChatQnA"

function App() {
  return (
    <MantineProvider>
      <Notifications position="top-right" />

      <div className="app-shell">
        <Navbar />

        <div className="chat-container">
          <Conversation title={title} />
        </div>
      </div>
    </MantineProvider>
  )
}

export default App
