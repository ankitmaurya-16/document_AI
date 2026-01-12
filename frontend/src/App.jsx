import React from 'react'
import { Route, Routes } from 'react-router-dom'
import ChatBox from './components/chatBox'
import Community from './pages/community'
import Sidebar from './components/sidebar'
import Credits from './pages/credits'
import Login from './pages/login'
import Loading from './pages/loading'
import { assets } from './assets/assets'
import { useState } from 'react'
import './assets/prism.css'
const App = () => {

  const [isMenuOpen, setIsMenuOpen]=useState(false)

  return (
    <>
    {!isMenuOpen && <img src={assets.menu_icon} className='absolute top-3 left-3 w-8 h-8 cursor-pointer md:hidden dark:invert' onClick={()=>setIsMenuOpen(true)}/>}
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
    </>
  )
}

export default App
