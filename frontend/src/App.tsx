import { lazy, Suspense, useState } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Loading from './pages/Loading'
import ChatBox from './components/ChatBox'
import Login from './pages/Login'
import { assets } from './assets/assets'
import './assets/prism.css'
import { useAppContext } from './context/AppContext'

// Heavy / rarely-used routes split into their own chunks.
const Credits = lazy(() => import('./pages/Credits'))
const Documents = lazy(() => import('./pages/Documents'))
const Community = lazy(() => import('./pages/Community'))

const App = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(() => window.innerWidth >= 768)
  const { pathname } = useLocation()
  const { user } = useAppContext()
  if (pathname === '/loading') {
    return <Loading />
  }
  return (
    <>
      {!isMenuOpen && (
        <img
          src={assets.menu_icon}
          className='absolute top-3 left-3 w-8 h-8 cursor-pointer dark:invert z-20'
          onClick={() => setIsMenuOpen(true)}
        />
      )}
      {user ? (
        <div className='dark:bg-gradient-to-br from-[#000000] via-[#0a0a0a] to-[#000000] dark:text-white'>
          <div className='flex h-screen w-screen'>
            <Sidebar isMenuOpen={isMenuOpen} setIsMenuOpen={setIsMenuOpen} />
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path='/' element={<ChatBox />} />
                <Route path='/credits' element={<Credits />} />
                <Route path='/documents' element={<Documents />} />
                <Route path='/community' element={<Community />} />
                <Route path='/login' element={<Login />} />
                <Route path='/loading' element={<Loading />} />
              </Routes>
            </Suspense>
          </div>
        </div>
      ) : (
        <div>
          <Login />
        </div>
      )}
    </>
  )
}

export default App
