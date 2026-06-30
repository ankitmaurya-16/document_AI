import React, { useEffect, useState } from 'react'
import { assets } from '../assets/assets'
import moment from 'moment'
import Markdown from 'react-markdown'
import { useAppContext } from '../context/AppContext'

const Message = ({ message, chatId }) => {
  const { submitFeedback, user } = useAppContext()
  const [rating, setRating] = useState(message.rating ?? 0)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    // Load Prism on demand so it lives in its own chunk (see vite.config.js
    // manualChunks). Assistant messages are the only thing that needs it.
    if (message.role !== 'assistant') return
    let cancelled = false
    import('prismjs').then(({ default: Prism }) => {
      if (!cancelled) Prism.highlightAll()
    })
    return () => { cancelled = true }
  }, [message.content, message.role])

  const vote = async (next) => {
    if (!user || !chatId) return
    const value = rating === next ? 0 : next
    setSubmitting(true)
    const ok = await submitFeedback({
      chatId,
      messageTimestamp: message.timestamp,
      rating: value,
    })
    setSubmitting(false)
    if (ok) setRating(value)
  }

  return (
    <div>
      {message.role === 'user' ? (
        <div className='flex items-start justify-end my-4 gap-2 pr-1'>
          <div className='flex flex-col gap-2 p-2 px-4 bg-blue-50 dark:bg-neutral-800/40 border border-neutral-300 dark:border-neutral-600/40 rounded-md max-w-2xl'>
            {message.files && message.files.length > 0 && (
              <div className='flex flex-wrap gap-2'>
                {message.files.map((fileName, index) => (
                  <div key={index} className='flex items-center gap-1 bg-gray-200 dark:bg-neutral-700/50 px-2 py-1 rounded text-xs'>
                    <span>📎</span>
                    <span className='dark:text-white'>{fileName}</span>
                  </div>
                ))}
              </div>
            )}
            {message.content && <p className=' text-sm dark:text-white'>{message.content}</p>}
            <span className='text-xs text-0gray-400 dark:text-gray-400'>{moment(message.timestamp).fromNow()}</span>
          </div>
          <img src={assets.user_icon} alt='' className='w-8 h-8 min-w-8 rounded-full ring-2 ring-[#2f198a] dark:ring-[#3D81F6]/60' />
        </div>
      ) : (
        <div className='inline-flex flex-col gap-2 p-2 px-4 max-w-2xl bg-gray-50 dark:bg-neutral-900/50 border border-neutral-200 dark:border-neutral-700/40 rounded-md my-4'>
          <div className='text-sm dark:text-white reset-tw'>
            <Markdown>{message.content}</Markdown>
          </div>

          {Array.isArray(message.sources) && message.sources.length > 0 && (
            <div className='flex flex-wrap items-center gap-1 pt-1'>
              <span className='text-xs text-gray-500 dark:text-neutral-400'>Sources:</span>
              {message.sources.map((src, i) => (
                <span
                  key={i}
                  title={src}
                  className='text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-blue-800/60'>
                  📄 {src}
                </span>
              ))}
            </div>
          )}

          <div className='flex items-center justify-between pt-1'>
            <span className='text-xs text-gray-400 dark:text-neutral-500'>{moment(message.timestamp).fromNow()}</span>
            {user && chatId && (
              <div className='flex items-center gap-1'>
                <button
                  disabled={submitting}
                  onClick={() => vote(1)}
                  title='Helpful'
                  className={`text-xs px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 ${rating === 1 ? 'text-green-600' : 'text-gray-400'}`}>
                  👍
                </button>
                <button
                  disabled={submitting}
                  onClick={() => vote(-1)}
                  title='Not helpful'
                  className={`text-xs px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 ${rating === -1 ? 'text-red-600' : 'text-gray-400'}`}>
                  👎
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default Message
