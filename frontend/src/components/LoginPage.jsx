import React, { useState } from 'react';
import { LogIn, UserPlus, Mail, Lock, User } from 'lucide-react';

export default function LoginPage({ onAuthSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const body =
      mode === 'login'
        ? { email, password }
        : { email, password, display_name: displayName };

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Authentication failed');
      }
      onAuthSuccess(data.user, data.tokens || data);
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/auth/demo', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Demo login failed');
      }
      onAuthSuccess(data.user, data.tokens || data);
    } catch (err) {
      setError(err.message || 'Demo mode unavailable');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">
          {mode === 'login' ? <LogIn size={28} /> : <UserPlus size={28} />}
          {mode === 'login' ? ' Welcome Back' : ' Create Account'}
        </h1>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          {mode === 'register' && (
            <div className="auth-field">
              <User size={18} className="auth-field-icon" />
              <input
                className="auth-input"
                type="text"
                placeholder="Display name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
              />
            </div>
          )}

          <div className="auth-field">
            <Mail size={18} className="auth-field-icon" />
            <input
              className="auth-input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <Lock size={18} className="auth-field-icon" />
            <input
              className="auth-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button className="auth-btn" type="submit" disabled={loading}>
            {loading
              ? 'Please wait…'
              : mode === 'login'
                ? 'Log In'
                : 'Register'}
          </button>
        </form>

        <button className="auth-demo-btn" onClick={handleDemo} disabled={loading}>
          Try Demo Mode
        </button>

        <div className="auth-toggle">
          {mode === 'login' ? (
            <>
              Don't have an account?{' '}
              <span onClick={() => setMode('register')}>Register</span>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <span onClick={() => setMode('login')}>Log In</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
