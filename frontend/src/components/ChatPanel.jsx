import React, { useState, useEffect, useRef } from 'react';

const API_URL = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

export default function ChatPanel({ token, currentUsername, onLogout }) {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [wsStatus, setWsStatus] = useState('connecting'); // connecting, open, closed
  
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const currentUserRef = useRef(null);

  // Fetch all users on mount
  useEffect(() => {
    const fetchUsersAndSelf = async () => {
      try {
        const res = await fetch(`${API_URL}/users`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          // Identify self and all other users
          const self = data.find(u => u.username === currentUsername);
          currentUserRef.current = self;
          
          const others = data.filter(u => u.username !== currentUsername);
          setUsers(others);
        } else if (res.status === 401) {
          onLogout();
        }
      } catch (err) {
        console.error('Error fetching users:', err);
      }
    };
    fetchUsersAndSelf();
  }, [token, currentUsername, onLogout]);

  // Connect WebSocket
  useEffect(() => {
    const connectWS = () => {
      setWsStatus('connecting');
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.hostname === 'localhost' ? 'localhost:8000' : `${window.location.hostname}:8000`;
      const wsUrl = `${wsProto}//${wsHost}/ws?token=${token}`;
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus('open');
      };

      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        
        if (payload.type === 'message' || payload.type === 'receipt') {
          const msgData = payload.data;
          
          // Append message if it belongs to current conversation
          setMessages(prev => {
            // Check if duplicate (e.g. if we already have it in state)
            if (prev.some(m => m.id === msgData.id)) return prev;
            
            // Only add if message is between current user and currently selected user
            const isRelevant = selectedUser && (
              (msgData.sender_id === currentUserRef.current?.id && msgData.receiver_id === selectedUser.id) ||
              (msgData.sender_id === selectedUser.id && msgData.receiver_id === currentUserRef.current?.id)
            );
            
            // Note: receipts are always relevant because they are our own sent messages
            if (isRelevant || payload.type === 'receipt') {
              return [...prev, msgData];
            }
            return prev;
          });
        } else if (payload.error) {
          console.error('WS Error:', payload.error);
        }
      };

      ws.onclose = () => {
        setWsStatus('closed');
        // Auto-reconnect after 3 seconds
        setTimeout(() => {
          if (token) connectWS();
        }, 3000);
      };

      ws.onerror = (err) => {
        console.error('WS Error event:', err);
        ws.close();
      };
    };

    connectWS();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [token, selectedUser]);

  // Fetch messages when selected user changes
  useEffect(() => {
    if (!selectedUser) return;

    const fetchMessages = async () => {
      try {
        const res = await fetch(`${API_URL}/messages/${selectedUser.id}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setMessages(data);
        }
      } catch (err) {
        console.error('Error fetching messages:', err);
      }
    };

    fetchMessages();
  }, [selectedUser, token]);

  // Auto-scroll messages to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!inputText.trim() || !selectedUser) return;

    if (wsRef.current && wsStatus === 'open') {
      const payload = {
        receiver_id: selectedUser.id,
        content: inputText.trim()
      };
      wsRef.current.send(JSON.stringify(payload));
      setInputText('');
    } else {
      alert('Connection lost. Trying to reconnect...');
    }
  };

  const handleDeleteMessage = async (messageId) => {
    if (!confirm('Are you sure you want to delete this message?')) return;
    try {
      const res = await fetch(`${API_URL}/messages/${messageId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        // Filter deleted message out of state
        setMessages(prev => prev.filter(m => m.id !== messageId));
      } else {
        const data = await res.json();
        alert(data.detail || 'Could not delete message.');
      }
    } catch (err) {
      console.error('Error deleting message:', err);
    }
  };

  const handleDeleteAccount = async () => {
    if (!currentUserRef.current) return;
    const confirmation = prompt('WARNING: Deleting your account will remove all message history and cannot be undone. Type "DELETE" to confirm:');
    if (confirmation !== 'DELETE') return;

    try {
      const res = await fetch(`${API_URL}/users/${currentUserRef.current.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        alert('Your account has been deleted.');
        onLogout();
      } else {
        const data = await res.json();
        alert(data.detail || 'Could not delete account.');
      }
    } catch (err) {
      console.error('Error deleting account:', err);
    }
  };

  const handleLogoutClick = async () => {
    try {
      await fetch(`${API_URL}/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
    } catch (err) {
      console.error('Logout request failed:', err);
    } finally {
      onLogout();
    }
  };

  const formatTime = (isoString) => {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex h-screen w-screen bg-brand-dark overflow-hidden font-sans">
      {/* Background ambient light */}
      <div className="absolute top-0 right-0 h-96 w-96 rounded-full bg-brand-primary/10 blur-3xl pointer-events-none"></div>
      
      {/* Sidebar - User List */}
      <div className="w-80 border-r border-brand-border backdrop-blur-md bg-brand-card/30 flex flex-col z-10">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-brand-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-gradient-to-tr from-brand-primary to-purple-400 flex items-center justify-center font-bold text-white uppercase shadow-md shadow-brand-primary/20">
              {currentUsername.slice(0, 2)}
            </div>
            <div>
              <h3 className="font-bold text-white leading-none">{currentUsername}</h3>
              <span className="text-xs text-emerald-400 flex items-center gap-1 mt-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Active Now
              </span>
            </div>
          </div>
          <button 
            onClick={handleLogoutClick}
            className="text-xs py-1.5 px-3 bg-red-950/45 hover:bg-red-900/40 border border-red-900/30 text-red-200 rounded-lg hover:shadow transition-all duration-150 cursor-pointer"
          >
            Logout
          </button>
        </div>

        {/* User Directory */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <h4 className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Conversations
          </h4>
          {users.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-gray-500">
              No other users registered.
            </div>
          ) : (
            users.map(u => {
              const isSelected = selectedUser && selectedUser.id === u.id;
              return (
                <button
                  key={u.id}
                  onClick={() => setSelectedUser(u)}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-150 text-left border cursor-pointer ${
                    isSelected 
                      ? 'bg-brand-primary/20 border-brand-primary/45 shadow-lg shadow-brand-primary/5' 
                      : 'border-transparent hover:bg-white/5'
                  }`}
                >
                  <div className="h-10 w-10 rounded-full bg-slate-700/80 border border-brand-border flex items-center justify-center font-bold text-gray-200 uppercase">
                    {u.username.slice(0, 2)}
                  </div>
                  <div>
                    <span className="font-medium block text-white">{u.username}</span>
                    <span className="text-xs text-gray-400">Click to chat</span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-brand-border bg-black/10">
          <button
            onClick={handleDeleteAccount}
            className="w-full py-2 px-3 text-center text-xs border border-dashed border-red-500/30 hover:border-red-500 text-red-400 hover:bg-red-500/10 rounded-xl transition-all duration-150 cursor-pointer"
          >
            Delete My Account
          </button>
        </div>
      </div>

      {/* Main Chat Panel */}
      <div className="flex-1 flex flex-col h-full bg-brand-dark/95 z-10">
        {selectedUser ? (
          <>
            {/* Chat Header */}
            <div className="h-16 border-b border-brand-border p-4 flex items-center justify-between backdrop-blur-md bg-brand-card/20">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-brand-primary/30 border border-brand-primary/40 flex items-center justify-center font-bold text-brand-primary uppercase">
                  {selectedUser.username.slice(0, 2)}
                </div>
                <div>
                  <h3 className="font-bold text-white">{selectedUser.username}</h3>
                  {/* WS Connection Status Indicator */}
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`h-2 w-2 rounded-full ${
                      wsStatus === 'open' 
                        ? 'bg-emerald-400 shadow shadow-emerald-400/50' 
                        : wsStatus === 'connecting' 
                          ? 'bg-amber-400 animate-pulse' 
                          : 'bg-red-500'
                    }`}></span>
                    <span className="text-[10px] text-gray-400 uppercase tracking-wide">
                      {wsStatus === 'open' ? 'WS Connected' : wsStatus === 'connecting' ? 'WS Reconnecting...' : 'WS Offline'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Messages Scroll Area */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-gray-500">
                  <p className="text-lg">No messages here yet.</p>
                  <p className="text-sm mt-1">Send a message to start the conversation!</p>
                </div>
              ) : (
                messages.map(m => {
                  const isOwn = m.sender_id === currentUserRef.current?.id;
                  return (
                    <div 
                      key={m.id} 
                      className={`flex w-full group ${isOwn ? 'justify-end' : 'justify-start'}`}
                    >
                      <div className="max-w-[70%] flex flex-col">
                        <div className={`relative px-4 py-2.5 rounded-2xl text-sm shadow-md transition-all duration-150 ${
                          isOwn 
                            ? 'bg-brand-primary text-white rounded-br-none' 
                            : 'bg-slate-800/80 border border-brand-border text-gray-100 rounded-bl-none'
                        }`}>
                          <p className="break-words leading-relaxed whitespace-pre-wrap">{m.content}</p>
                          
                          {/* Hover delete trigger (only own messages) */}
                          {isOwn && (
                            <button
                              onClick={() => handleDeleteMessage(m.id)}
                              className="absolute top-1/2 -left-8 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1.5 bg-red-950/60 border border-red-500/30 text-red-400 hover:text-red-300 rounded-lg hover:shadow-lg transition-all duration-150 cursor-pointer"
                              title="Delete message"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                              </svg>
                            </button>
                          )}
                        </div>
                        <span className={`text-[10px] text-gray-500 mt-1 ${isOwn ? 'text-right' : 'text-left'}`}>
                          {formatTime(m.timestamp)}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Message Form */}
            <form onSubmit={handleSendMessage} className="p-4 border-t border-brand-border bg-black/10 flex gap-3">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="Type your message here..."
                className="flex-1 px-4 py-3 bg-slate-900/40 border border-brand-border rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-brand-primary focus:border-transparent transition-all duration-150"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className="py-3 px-6 bg-brand-primary hover:bg-brand-primary-hover text-white font-bold rounded-xl shadow-md transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Send
              </button>
            </form>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            {/* Aesthetic chat illustration/icon */}
            <div className="h-24 w-24 rounded-full bg-brand-primary/10 border border-brand-primary/20 flex items-center justify-center text-brand-primary mb-6 animate-pulse">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white">Your Encrypted Workstation</h2>
            <p className="text-gray-400 mt-2 max-w-sm text-sm">
              Select any contact in the sidebar to load your one-to-one conversation logs and establish secure real-time messaging.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
