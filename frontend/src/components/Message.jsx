import React, { useEffect } from 'react'
import { assets } from '../assets/assets'
import moment from 'moment'
import Markdown from 'react-markdown'
import Prism from 'prismjs'
const Message = ({message}) => {
    useEffect(()=>{
        Prism.highlightAll()
    },[message.content])
  return (
    <div>
      {message.role==='user'? (
        <div className='flex items-start justify-end my-4 gap-2'>
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
            <img src={assets.user_icon} alt="" className='w-8 rounded-full ring-2 ring-[#2f198a] dark:ring-[#3D81F6]/60' />
        </div>
      ):(
        <div className='inline-flex flex-col gap-2 p-2 px-4 max-w-2xl bg-gray-50 dark:bg-neutral-900/50 border border-neutral-200 dark:border-neutral-700/40 rounded-md my-4'>
            {(<div className='text-sm dark:text-white reset-tw'>
                <Markdown>{message.content}</Markdown>
                </div>)}
            <span className='text-xs text-gray-400 dark:text-neutral-500'>{moment(message.timestamp).fromNow()}</span>
        </div>
      )}
    </div>
  )
}

export default Message
