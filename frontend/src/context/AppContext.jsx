import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const API_URL = "http://localhost:5001";

const AppContext = createContext()
export const AppContextProvider=({ children })=>{
    const navigate = useNavigate()
    const [user, setUser] = useState(null);
    const [chats, setChats] = useState([]);
    const [selectedChat, setSelectedChat] = useState(null);
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');
    const [token, setToken] = useState(localStorage.getItem('token') || null);
    const [loading, setLoading] = useState(true);

    // Get auth headers
    const getAuthHeaders = () => ({
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    });

    // Verify token and fetch user on app load
    const verifyAuth = async () => {
        const storedToken = localStorage.getItem('token');
        if (!storedToken) {
            setLoading(false);
            return;
        }
        
        try {
            const res = await fetch(`${API_URL}/api/auth/verify`, {
                headers: { 'Authorization': `Bearer ${storedToken}` }
            });
            
            if (res.ok) {
                const data = await res.json();
                setUser(data.user);
                setToken(storedToken);
            } else {
                // Token invalid, clear it
                localStorage.removeItem('token');
                setToken(null);
                setUser(null);
            }
        } catch (error) {
            console.error('Auth verification failed:', error);
            localStorage.removeItem('token');
            setToken(null);
        } finally {
            setLoading(false);
        }
    };

    // Refresh user data (to update credits after queries)
    const refreshUser = async () => {
        if (!token) return;
        try {
            const res = await fetch(`${API_URL}/api/auth/verify`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setUser(data.user);
            }
        } catch (error) {
            console.error('Failed to refresh user:', error);
        }
    };

    // Login
    const login = async (email, password) => {
        try {
            const res = await fetch(`${API_URL}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            
            const data = await res.json();
            
            if (res.ok) {
                localStorage.setItem('token', data.token);
                setToken(data.token);
                setUser(data.user);
                return { success: true };
            } else {
                return { success: false, error: data.error };
            }
        } catch (error) {
            return { success: false, error: 'Network error' };
        }
    };

    // Register
    const register = async (name, email, password) => {
        try {
            const res = await fetch(`${API_URL}/api/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, password })
            });
            
            const data = await res.json();
            
            if (res.ok) {
                localStorage.setItem('token', data.token);
                setToken(data.token);
                setUser(data.user);
                return { success: true };
            } else {
                return { success: false, error: data.error };
            }
        } catch (error) {
            return { success: false, error: 'Network error' };
        }
    };

    // Google OAuth Login
    const googleLogin = async (accessToken) => {
        try {
            const res = await fetch(`${API_URL}/api/auth/google`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ access_token: accessToken })
            });
            
            const data = await res.json();
            
            if (res.ok) {
                localStorage.setItem('token', data.token);
                setToken(data.token);
                setUser(data.user);
                return { success: true };
            } else {
                return { success: false, error: data.error };
            }
        } catch (error) {
            return { success: false, error: 'Network error' };
        }
    };

    // Logout
    const logout = () => {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
        setChats([]);
        setSelectedChat(null);
        navigate('/login');
    };

    // Fetch user chats
    const fetchUserChats = async () => {
        if (!token) return;
        
        try {
            const res = await fetch(`${API_URL}/api/chats`, {
                headers: getAuthHeaders()
            });
            
            if (res.ok) {
                const data = await res.json();
                setChats(data.chats);
                // Select first chat if none selected
                if (data.chats.length > 0 && !selectedChat) {
                    setSelectedChat(data.chats[0]);
                }
            }
        } catch (error) {
            console.error('Failed to fetch chats:', error);
        }
    };

    // Create new chat
    const createNewChat = async (name = 'New Chat') => {
        if (!token) return null;
        
        try {
            const res = await fetch(`${API_URL}/api/chats`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ name })
            });
            
            if (res.ok) {
                const data = await res.json();
                setChats(prev => [data.chat, ...prev]);
                setSelectedChat(data.chat);
                return data.chat;
            }
        } catch (error) {
            console.error('Failed to create chat:', error);
        }
        return null;
    };

    // Delete chat
    const deleteChat = async (chatId) => {
        if (!token) return false;
        
        try {
            const res = await fetch(`${API_URL}/api/chats/${chatId}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });
            
            if (res.ok) {
                setChats(prev => prev.filter(c => c._id !== chatId));
                if (selectedChat?._id === chatId) {
                    setSelectedChat(chats.find(c => c._id !== chatId) || null);
                }
                return true;
            }
        } catch (error) {
            console.error('Failed to delete chat:', error);
        }
        return false;
    };

    // Update chat in state (after new message)
    const updateChatInState = (chatId, messages) => {
        setChats(prev => prev.map(c => 
            c._id === chatId ? { ...c, messages, updatedAt: new Date().toISOString() } : c
        ));
        if (selectedChat?._id === chatId) {
            setSelectedChat(prev => ({ ...prev, messages, updatedAt: new Date().toISOString() }));
        }
    };

    // Refresh a specific chat from server
    const refreshChat = async (chatId) => {
        if (!token) return null;
        
        try {
            const res = await fetch(`${API_URL}/api/chats/${chatId}`, {
                headers: getAuthHeaders()
            });
            
            if (res.ok) {
                const data = await res.json();
                console.log('Refreshed chat data:', data.chat);
                console.log('Messages timestamps:', data.chat.messages?.map(m => ({ content: m.content?.slice(0,20), timestamp: m.timestamp, parsed: new Date(m.timestamp) })));
                setChats(prev => prev.map(c => c._id === chatId ? data.chat : c));
                setSelectedChat(data.chat);
                return data.chat;
            }
        } catch (error) {
            console.error('Failed to refresh chat:', error);
        }
        return null;
    };
    
    useEffect(()=>{
        if(theme==='dark'){
            document.documentElement.classList.add('dark');
        }
        else{
            document.documentElement.classList.remove('dark');
        }
        localStorage.setItem('theme', theme)
    },[theme])

    useEffect(()=>{
        if(user && token){
            fetchUserChats()
        }
        else{
            setChats([])
            setSelectedChat(null)
        }
    }, [user, token])

    useEffect(()=>{
        verifyAuth()
    },[])

    const value = {
        navigate, 
        user, setUser, 
        token,
        login, register, logout, googleLogin,
        chats, setChats, 
        selectedChat, setSelectedChat, 
        theme, setTheme,
        loading,
        fetchUserChats,
        createNewChat,
        deleteChat,
        updateChatInState,
        refreshChat,
        refreshUser,
        API_URL
    }
    return (
        <AppContext.Provider value={value}>
            {children}
        </AppContext.Provider>
    )
}
export const useAppContext = ()=> useContext(AppContext)