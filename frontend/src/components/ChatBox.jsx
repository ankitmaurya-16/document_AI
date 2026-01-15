import React, { useEffect, useRef, useState } from 'react'
import { useAppContext } from '../context/AppContext'
import { assets } from '../assets/assets'
import Message from './message'

const ChatBox = () => {
    const containerRef = useRef(null)
    const fileInputRef = useRef(null)
    const { selectedChat, theme } = useAppContext()
    const [messages, setMessages] = useState([])
    const [loading, setLoading] = useState(false)
    const [prompt, setPrompt] = useState('')
    const [selectedFile, setSelectedFile] = useState(null)

    const handleFileChange = (e) => {
        const file = e.target.files[0]
        if (file) {
            setSelectedFile(file)
        }
    }

    const removeFile = () => {
        setSelectedFile(null)
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
    }

    const onSubmit = async (e) => {
        e.preventDefault()
        if (!prompt.trim() && !selectedFile) return

        setLoading(true)
        try {
            const formData = new FormData()
            formData.append('prompt', prompt)
            if (selectedFile) {
                formData.append('file', selectedFile)
            }

            const response = await fetch('http://localhost:5000/api/chat/upload', {
                method: 'POST',
                body: formData,
            })

            if (response.ok) {
                const data = await response.json()
                // Add the response to messages
                setMessages(prev => [...prev, 
                    { role: 'user', content: prompt, file: selectedFile?.name },
                    { role: 'assistant', content: data.response }
                ])
                setPrompt('')
                setSelectedFile(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
            }
        } catch (error) {
            console.error('Error:', error)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (selectedChat) {
            setMessages(selectedChat.messages)
        }
    }, [selectedChat])

    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.scrollTo({
                top: containerRef.current.scrollHeight, behavior: "smooth",
            })
        }
    }, [messages])

    return (
        <div className='flex-1 flex flex-col justify-between m-5 md:m-10 xl:mx-30 max-md:mt-14 2xl:pr-40'>
            {/**Chat message */}
            <div ref={containerRef} className='flex-1 mb-5 overflow-y-scroll'>
                {messages.length === 0 && (
                    <div className='h-full flex flex-col items-center justify-center gap-2 text-primary'>
                        <img src={assets.logo_full} className='w-full max-w-80 sm:max-w-120' />
                        <p className='mt-5 text-4xl sm:text-6xl text-center text-gray-400 dark:text-white-300'>Ask me</p>
                    </div>
                )}
                {messages.map((message, index) => <Message key={index} message={message} />)}

                {/* Three dot loading  */}
                {loading && (
                    <div className='loader flex items-center gap-1.5'>
                        <div className='w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce'></div>
                        <div className='w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce'></div>
                        <div className='w-1.5 h-1.5 rounded-full bg-gray-500 dark:bg-white animate-bounce'></div>
                    </div>
                )}
            </div>

            {/* File preview */}
            {selectedFile && (
                <div className='max-w-2xl mx-auto w-full mb-2 px-4'>
                    <div className='inline-flex items-center gap-2 bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 text-sm'>
                        <span>📎 {selectedFile.name}</span>
                        <button type="button" onClick={removeFile} className='text-red-500 hover:text-red-700'>✕</button>
                    </div>
                </div>
            )}

            {/**Prompt Input Box */}
            <form onSubmit={onSubmit} className='bg-white/20 dark:bg-black/30 border border-primary dark:border-[#80609F]/30 rounded-full w-full max-w-2xl p-3 pl-4 mx-auto flex gap-4 items-center'>
                {/* Hidden file input */}
                <input
                    ref={fileInputRef}
                    type="file"
                    onChange={handleFileChange}
                    className='hidden'
                    accept='.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.csv,.xlsx'
                />
                
                {/* Upload button */}
                <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className='p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors'
                    title="Upload file"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                </button>

                <input 
                    onChange={(e) => setPrompt(e.target.value)} 
                    value={prompt} 
                    type="text" 
                    placeholder='Type a message...' 
                    className='flex-1 w-full text-sm outline-none bg-transparent' 
                />
                
                <button disabled={loading || (!prompt.trim() && !selectedFile)}>
                    <img src={loading ? assets.stop_icon : assets.send_icon} className='w-8 cursor-pointer' alt="" />
                </button>
            </form>
        </div>
    )
}

export default ChatBox