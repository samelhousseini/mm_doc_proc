// app/routes/index.tsx
import React, { useEffect, useState } from "react"
import { Box, Flex, Heading, Button, Input, Text, Switch, FormControl, FormLabel, useColorMode, useColorModeValue } from "@chakra-ui/react"
import axios from "axios"

// Chainlit hooks
import { useChatSession, useChatMessages, useChatInteract } from "@chainlit/react-client"

interface ChatMessage {
  role: string
  content: string
}
interface ChatRunStep {
  step_type: string
  status: string
}
interface ChatResponse {
  agent_id: string
  thread_id: string
  run_id?: string
  status: string
  messages: ChatMessage[]
  run_steps: ChatRunStep[]
  file_ids: string[]
}

export default function Index() {
  const [userId, setUserId] = useState("alice")
  const [message, setMessage] = useState("")
  const [newChat, setNewChat] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)

  // chainlit
  const { connect, disconnect } = useChatSession()
  const { messages } = useChatMessages()
  const { sendMessage, clear } = useChatInteract()

  // color mode
  const { toggleColorMode } = useColorMode()
  const bg = useColorModeValue("gray.100", "gray.800")
  const textColor = useColorModeValue("gray.800", "gray.100")

  useEffect(() => {
    // Connect to chainlit client on mount
    connect()
    return () => {
      disconnect()
    }
  }, [])

  async function handleSend() {
    if (!message.trim()) return

    try {
      const resp = await axios.post<ChatResponse>("http://localhost:8000/chat", {
        user_id: userId,
        message,
        new_chat: newChat
      })
      const data = resp.data

      if (newChat) {
        clear()
      }

      setThreadId(data.thread_id)

      // push each message to chainlit store
      data.messages.forEach((m) => {
        sendMessage({
          id: crypto.randomUUID(),
          content: m.content,
          author: m.role
        })
      })

    } catch (err) {
      console.error("Error calling /chat:", err)
    }

    setMessage("")
    setNewChat(false)
  }

  return (
    <Flex direction="column" w="100%" h="100%" bg={bg} color={textColor}>
      {/* Header */}
      <Flex bg="teal.600" p={4} justify="space-between" align="center">
        <Heading size="md" color="white">
          Remix + Chainlit Demo
        </Heading>
        <Button variant="outline" colorScheme="whiteAlpha" onClick={toggleColorMode}>
          Toggle Theme
        </Button>
      </Flex>

      <Flex flex="1" overflow="hidden">
        {/* Sidebar */}
        <Box w="250px" p={4} bg="gray.300" color="gray.800" overflowY="auto">
          <Heading size="sm" mb={4}>Settings</Heading>
          
          <FormControl mb={4}>
            <FormLabel>User ID</FormLabel>
            <Input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            />
          </FormControl>

          <FormControl display="flex" alignItems="center" mb={4}>
            <FormLabel mb="0">New Chat?</FormLabel>
            <Switch 
              isChecked={newChat}
              onChange={(e) => setNewChat(e.target.checked)}
            />
          </FormControl>

          <Text fontSize="sm">Thread: {threadId || "(none)"}</Text>
        </Box>

        {/* Main Chat area */}
        <Flex direction="column" flex="1" p={4}>
          <Box flex="1" overflowY="auto" mb={4} border="1px" borderColor="gray.400" borderRadius="md" p={4}>
            {messages.map((msg) => (
              <Box key={msg.id} mb={2}>
                <Text fontWeight="bold">{msg.author}</Text>
                <Text>{msg.content}</Text>
              </Box>
            ))}
          </Box>

          {/* Input row */}
          <Flex>
            <Input
              placeholder="Type a message..."
              flex="1"
              mr={2}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <Button colorScheme="teal" onClick={handleSend}>
              Send
            </Button>
          </Flex>
        </Flex>
      </Flex>
    </Flex>
  )
}
