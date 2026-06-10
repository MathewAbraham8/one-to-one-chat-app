import React, { useState } from 'react';
import Auth from './components/Auth';
import ChatPanel from './components/ChatPanel';

export default function App() {
  const [token, setToken] = useState(() => {
    // Standard in-memory state. We do NOT store in localStorage to prevent XSS.
    return null;
  });
  const [username, setUsername] = useState('');

  const handleLoginSuccess = (receivedToken, loggedUsername) => {
    setToken(receivedToken);
    setUsername(loggedUsername);
  };

  const handleLogout = () => {
    setToken(null);
    setUsername('');
  };

  if (!token) {
    return <Auth onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <ChatPanel 
      token={token} 
      currentUsername={username} 
      onLogout={handleLogout} 
    />
  );
}
