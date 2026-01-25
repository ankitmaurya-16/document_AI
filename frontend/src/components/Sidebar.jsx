import React, { useState } from 'react'
import { useAppContext } from '../context/AppContext'
import { assets } from '../assets/assets'
import moment from 'moment/moment'
const Sidebar = ({isMenuOpen, setIsMenuOpen}) => {

    const {chats, setSelectedChat, theme, setTheme, user, navigate} = useAppContext()
    const [search, setSearch] = useState('')

  return (
    <div
        className={`flex flex-col h-screen min-w-72 p-5
        dark:bg-gradient-to-b from-[#242124]/30 to-[#000000]/30
        border-r border-[#80609F]/30 backdrop-blur-3xl
        transition-all duration-500
        max-md:absolute left-0 z-10
        ${!isMenuOpen && 'max-md:-translate-x-full md:hidden'}`}
        >

      <img src={assets.logo_full} alt="" className='w-full max-w-48'/>
      {/* New chat button */}
      <button className='flex justify-center items-center w-full py-2 mt-10 text-white bg-gradient-to-r from-[#2f198a] to-[#3D81F6] text-sm rounded-md cursor-pointer'>
        <span className='mr-2 text-xl'>+</span> New Chat
      </button>
      {/* search conversation */}
      <div className='flex items-center gap-2 p-3 mt-4 border border-gray-400 dark:border-white/20 rounded-md'>
      <img src={assets.search_icon} className='w-4 not-dark:invert' alt="" />
      <input onChange={(e)=>setSearch(e.target.value)} value={search} type='text' placeholder='Search Conversation' className='text-xs placeholder:text-gray-400 outline-none'/>
      </div>
      {/** recent chats */}
      {chats.length>0 && <p className='mt-4 text-sm'>Recent Chats</p>}
      <div className='flex-1 overflow-y-scrol mt-3 text-sm space-y-3'>
        {
            chats
                .filter((chat) => {
                    const query = search.toLowerCase()

                    const firstMessage = chat.messages?.[0]?.content?.toLowerCase()
                    const chatName = chat.name?.toLowerCase()

                    return (
                    firstMessage?.includes(query) ||
                    chatName?.includes(query)
                    )
                })
                .map((chat) => (
                    <div onClick ={()=>{navigate('/'); setSelectedChat(chat);setIsMenuOpen(false)}} key={chat._id} className='p-2 px-4 dark:bg-[#2f198a]/10 border border-gray-300 dark:border-[#80609F]/15
                    rounded-md cursor-pointer
                    flex justify-between group/chat'>
                        <div>   
                        <p className='truncate w-full'>
                            {
                                chat.messages.length>0?chat.messages[0].content.slice(0,32):chat.name
                            }
                        </p>
                        <p className='text-xs text-gray-500 dark:text-[#B1A6C0]'>
                            {moment(chat.updatedAt).fromNow()}
                        </p>
                        </div> 
                            <img src={assets.bin_icon} className='max-md:block hidden group-hover/chat:block w-4 cursor-pointer not-dark:invert'/>
                    </div>
                ))

        }
      </div>
      {/** Community images */}
      {/* <div onClick={()=>{navigate('/community');setIsMenuOpen(false)}} className='flex items-center gap-2 p-3 mt-4 border border-gray-300
      dark:border-white/15 rounded-md cursor-pointer hover:scale-103 transition-all'>
        <img
        src={assets.gallery_icon}
        className="w-4.5 invert dark:invert-0"
        />

        <div className='flex flex-col text-sm'>
            <p>Community Images</p>
        </div>
      </div> */}

        {/** Credit Purchases Option */}
      <div onClick={()=>{navigate('/credits');setIsMenuOpen(false)}} className='flex items-center gap-2 p-3 mt-4 border border-gray-300
      dark:border-white/15 rounded-md cursor-pointer hover:scale-103 transition-all'>
        <img
        src={assets.diamond_icon}
        className="w-4.5 dark:invert"
        />

        <div className='flex flex-col text-sm'>
            <p>Credits : {user?.credits}</p>
            <p className='text-xs text-gray-400'>Purchase credits to use DocAI</p>
        </div>
      </div>
        {/** Dark Mode Toggle */}
        <div className='flex items-center justify-between gap-2 p-3 mt-4 border border-gray-300
      dark:border-white/15 rounded-md'>
        
        <div className='flex items-center gap-2 text-sm'>
            <img src={assets.theme_icon} className='w-4 not-dark:invert' alt="" />
            <p>Dark Mode</p>
        </div>
        <label className='relative inline-flex cursor-pointer'>
            <input onChange = {()=>setTheme(theme==='dark'?'light':'dark')} type="checkbox" className='sr-only peer' checked={theme === 'dark'} />
            <div className='w-9 h-5 bg-gray-400 rounded-full peer-checked:bg-[#3D81F6]
                transition-all'></div>
            <span className='absolute left-1 top-1 w-3 h-3 bg-white rounded-full transition-trasnform peer-checked:translate-x-4'></span>
        </label>
      </div>
    {/** User account */}
      <div className='flex items-center gap-3 p-3 mt-4 border border-gray-300
      dark:border-white/15 rounded-md cursor-pointer group/user'>
        <img
        src={assets.user_icon}
        className="w-7 rounded-full"
        />
        <p className='flex-1 text-sm dark:text-primary truncate'>{user?user.name:'Login your account'}</p>
        {user && <img src={assets.logout_icon} className='h-5 cursor-pointer max-md:block hidden not-dark:invert group-hover/user:block'/>}
      </div>

        <div className='group/close absolute top-3 right-3 p-1'>
          <img onClick={()=>setIsMenuOpen(false)} src={assets.close_icon} className='w-5 h-5 cursor-pointer not-dark:invert max-md:opacity-100 opacity-0 group-hover/close:opacity-100 transition-opacity duration-300'/>
        </div>

    </div>
    
    
    
  )
}

export default Sidebar
 