import React, { useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

export default function Auth({ onLoginSuccess }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const validateInputs = () => {
    if (username.length < 3 || username.length > 30) {
      setError('Username must be between 3 and 30 characters.');
      return false;
    }
    // Alphanumeric + underscore/hyphen
    const usernameRegex = /^[a-zA-Z0-9_-]+$/;
    if (!usernameRegex.test(username)) {
      setError('Username can only contain letters, numbers, underscores, and hyphens.');
      return false;
    }
    if (password.length < 12) {
      setError('Password must be at least 12 characters.');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!validateInputs()) return;

    setLoading(true);
    const endpoint = isLogin ? '/login' : '/register';
    const payload = isLogin 
      ? { username, password }
      : { username, password }; // same body structure for both

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'An error occurred. Please try again.');
      }

      if (isLogin) {
        onLoginSuccess(data.access_token, username);
      } else {
        setSuccess('Registration successful! You can now log in.');
        setIsLogin(true);
        setPassword('');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-dark px-4 py-12 sm:px-6 lg:px-8">
      {/* Visual background ambient blobs */}
      <div className="absolute top-1/4 left-1/4 h-72 w-72 rounded-full bg-brand-primary/20 blur-3xl"></div>
      <div className="absolute bottom-1/4 right-1/4 h-80 w-80 rounded-full bg-blue-500/10 blur-3xl"></div>

      <div className="relative w-full max-w-md backdrop-blur-md bg-brand-card/85 border border-brand-border shadow-2xl rounded-2xl p-8 transition-all duration-300">
        <div className="text-center mb-8">
          <h2 className="text-4xl font-extrabold tracking-tight text-white">
            {isLogin ? 'Welcome Back' : 'Create Account'}
          </h2>
          <p className="mt-2 text-sm text-gray-400">
            {isLogin ? 'Sign in to connect with friends' : 'Sign up to start chatting'}
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/35 border border-red-500/50 text-red-200 text-sm text-center">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 rounded-lg bg-emerald-900/35 border border-emerald-500/50 text-emerald-200 text-sm text-center">
            {success}
          </div>
        )}

        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 bg-brand-dark/50 border border-brand-border rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-primary focus:border-transparent transition-all duration-200"
              placeholder="e.g. alex_chat"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 bg-brand-dark/50 border border-brand-border rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-primary focus:border-transparent transition-all duration-200"
              placeholder="••••••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 bg-brand-primary hover:bg-brand-primary-hover text-white font-bold rounded-xl shadow-lg hover:shadow-brand-primary/20 transform hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {loading ? 'Processing...' : isLogin ? 'Sign In' : 'Sign Up'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={() => {
              setIsLogin(!isLogin);
              setError('');
              setSuccess('');
            }}
            className="text-sm text-brand-primary hover:text-brand-primary-hover font-semibold transition-all duration-150 cursor-pointer"
          >
            {isLogin ? "Don't have an account? Sign Up" : 'Already have an account? Sign In'}
          </button>
        </div>
      </div>
    </div>
  );
}
