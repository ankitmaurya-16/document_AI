import React, { use, useLayoutEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import ChatBox from './components/chatBox'
import Community from './pages/community'
import Sidebar from './components/sidebar'
import Credits from './pages/credits'
import Login from './pages/login'
import Loading from './pages/Loading'
import { assets } from './assets/assets'
import { useState } from 'react'
import './assets/prism.css'
import { useAppContext } from './context/AppContext'
  const App = () => {

  const [isMenuOpen, setIsMenuOpen]=useState(() => window.innerWidth >= 768)
  const {pathname} = useLocation()
  const {user} = useAppContext()
  if (pathname === '/loading') {
    return <Loading/>
  }
  return (
    <>
    {!isMenuOpen && <img src={assets.menu_icon} className='absolute top-3 left-3 w-8 h-8 cursor-pointer dark:invert z-20' onClick={()=>setIsMenuOpen(true)}/>}
      {user?(
        <div className='dark:bg-gradient-to-b from-[#242124] to-[#000000] dark:text-white'>
        <div className='flex h-screen w-screen'>
          <Sidebar isMenuOpen={isMenuOpen} setIsMenuOpen={setIsMenuOpen}/>
          <Routes>
            <Route path='/' element={<ChatBox/>}/>
            <Route path='/credits' element={<Credits/>}/>
            <Route path='/community' element={<Community/>}/>
            <Route path='/login' element={<Login/>}/>
            <Route path='/loading' element={<Loading/>}/>
          </Routes>
        </div>
      </div>
      ):(
        <div><Login/></div>
      )}
      
    </>
  )
}

export default App
