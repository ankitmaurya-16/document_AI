import React, { useEffect, useRef, useState } from "react"
import { useAppContext } from "../context/AppContext"
import { assets } from "../assets/assets"
import Message from "./message"

const ChatBox = () => {
  const containerRef = useRef(null)
  const fileInputRef = useRef(null)

  const { selectedChat, setSelectedChat, token, API_URL, createNewChat, fetchUserChats, user, refreshUser } = useAppContext()

  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [prompt, setPrompt] = useState("")
  const [selectedFiles, setSelectedFiles] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) {
      setSelectedFiles((prev) => [...prev, ...files])
    }
  }

  const removeFile = (indexToRemove) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== indexToRemove))
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const clearAllFiles = () => {
    setSelectedFiles([])
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const onSubmit = async (e) => {
  e.preventDefault()
  if (!prompt.trim() && selectedFiles.length === 0) return

  const currentPrompt = prompt
  const currentFiles = selectedFiles

  setPrompt("")
  clearAllFiles()

  setLoading(true)

  // Add user message to UI immediately
  const userMessage = {
    role: "user",
    content: currentPrompt,
    files: currentFiles.map((f) => f.name),
    timestamp: Date.now()
  }

  setMessages((prev) => [...prev, userMessage])

  try {
    // Build headers with auth token if available
    const headers = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    if (currentFiles.length === 0) {
      // Chat without files
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ 
          prompt: currentPrompt,
          chatId: currentChatId 
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        if (data.credits_exhausted) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "⚠️ Credits exhausted! Please purchase more credits to continue using DocAI.", timestamp: Date.now() },
          ])
          setLoading(false)
          return
        }
        throw new Error(data.error || "Request failed")
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, timestamp: Date.now() },
      ])

      // Refresh chats and user credits if authenticated
      if (token && data.chatId) {
        setCurrentChatId(data.chatId)
        fetchUserChats()
        refreshUser()
      }
    }
    else if (currentFiles.length > 0 && currentPrompt.trim() === "") {
      // Upload files only
      const formData = new FormData()
      currentFiles.forEach((file) => {
        formData.append("files", file)
      })
      
      const response = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        headers,
        body: formData,
      })

      if (!response.ok) throw new Error("Upload failed")

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "File Upload successful!", timestamp: Date.now() },
      ])
    }
    else {
      // Chat with files
      const formData = new FormData()
      formData.append("prompt", currentPrompt)
      if (currentChatId) {
        formData.append("chatId", currentChatId)
      }

      currentFiles.forEach((file) => {
        formData.append("files", file)
      })
      
      const response = await fetch(`${API_URL}/api/chat/upload`, {
        method: "POST",
        headers,
        body: formData,
      })

      const data = await response.json()

      if (!response.ok) {
        if (data.credits_exhausted) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "⚠️ Credits exhausted! Please purchase more credits to continue using DocAI.", timestamp: Date.now() },
          ])
          setLoading(false)
          return
        }
        throw new Error(data.error || "Upload failed")
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, timestamp: Date.now() },
      ])

      // Update current chat ID and refresh chats/credits if authenticated
      if (token && data.chatId) {
        setCurrentChatId(data.chatId)
        fetchUserChats()
        refreshUser()
      }
    }
  } catch (error) {
    console.error(error)
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "Something went wrong. Try again.", timestamp: Date.now() },
    ])
  } finally {
    setLoading(false)
  }
}


  useEffect(() => {
    if (selectedChat) {
      setMessages(selectedChat.messages || [])
      setCurrentChatId(selectedChat._id)
    } else {
      setMessages([])
      setCurrentChatId(null)
    }
  }, [selectedChat])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth",
      })
    }
  }, [messages])

  return (
    <div className="flex-1 flex flex-col justify-between m-5 md:m-10 xl:mx-30 max-md:mt-14">
      {/* Chat messages */}
      <div ref={containerRef} className="flex-1 mb-5 overflow-y-scroll max-w-2xl mx-auto w-full">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-primary">
            <img
              src={assets.logo_full}
              className="w-full max-w-80 sm:max-w-120"
              alt="logo"
            />
            <p className="mt-5 text-4xl sm:text-6xl text-center text-gray-400 dark:text-white-300">
              Ask me
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <Message key={index} message={message} />
        ))}

        {/* Loading dots */}
        {loading && (
          <div className="loader flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce"></div>
          </div>
        )}
      </div>

      {/* File preview list */}
      {selectedFiles.length > 0 && (
        <div className="max-w-2xl mx-auto w-full mb-2 px-4">
          <div className="flex flex-wrap gap-2">
            {selectedFiles.map((file, index) => (
              <div
                key={index}
                className="inline-flex items-center gap-2 bg-gray-100 dark:bg-black/60 rounded-lg px-3 py-2 text-sm"
              >
                <span>📎 {file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="text-red-500 hover:text-red-700"
                  title="Remove file"
                >
                  ✕
                </button>
              </div>
            ))}

            <button
              type="button"
              onClick={clearAllFiles}
              className="text-xs px-3 py-2 rounded-lg bg-gray-200 dark:bg-black/70 hover:opacity-80"
              title="Remove all files"
            >
              Clear all
            </button>
          </div>
        </div>
      )}

      {/* Prompt input box */}
      <form
        onSubmit={onSubmit}
        className="bg-white/20 dark:bg-black/50 border border-primary dark:border-white/20 rounded-full w-full max-w-2xl p-3 pl-4 mx-auto flex gap-4 items-center"
      >
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          className="hidden"
          accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.csv,.xlsx"
        />

        {/* Upload button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="p-2 hover:bg-gray-200 dark:hover:bg-black/60 rounded-full transition-colors"
          title="Upload files"
          disabled={loading}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
            />
          </svg>
        </button>

        {/* Prompt input */}
        <input
          onChange={(e) => setPrompt(e.target.value)}
          value={prompt}
          type="text"
          placeholder="Type a message..."
          className="flex-1 w-full text-sm outline-none bg-transparent"
        />

        {/* Send button */}
        <button
          disabled={loading || (!prompt.trim() && selectedFiles.length === 0)}
        >
          <img
            src={loading ? assets.stop_icon : assets.send_icon}
            className="w-8 cursor-pointer"
            alt="send"
          />
        </button>
      </form>
    </div>
  )
}

export default ChatBox
