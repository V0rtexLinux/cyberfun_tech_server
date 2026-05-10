'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { createSession, getSession, clearSession, hasFaceRegistered, clearFaceDescriptors } from '../../lib/security'

// Dynamically import to avoid SSR issues with browser APIs
const FaceRecognition = dynamic(() => import('../../components/FaceRecognition'), {
  ssr: false,
  loading: () => (
    <div style={{ height: '320px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <p style={{ color: '#444', fontSize: '13px' }}>Initializing...</p>
    </div>
  ),
})

export default function AuthPage() {
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [authState, setAuthState] = useState('idle') // idle | success | error
  const [message, setMessage] = useState('')
  const [session, setSession] = useState(null)
  const [hasRegistered, setHasRegistered] = useState(false)

  useEffect(() => {
    const existing = getSession()
    setSession(existing)
    setHasRegistered(hasFaceRegistered())
  }, [])

  const handleSuccess = (label, distance) => {
    setAuthState('success')
    if (mode === 'register') {
      setMessage('Face registered. You can now log in.')
      setHasRegistered(true)
      setTimeout(() => setMode('login'), 2000)
    } else {
      const sess = createSession(label)
      setSession(sess)
      setMessage(`Welcome back! Session active for 1 hour.`)
    }
  }

  const handleError = (err) => {
    setAuthState('error')
    setMessage(err || 'Authentication failed.')
  }

  const handleLogout = () => {
    clearSession()
    setSession(null)
    setAuthState('idle')
    setMessage('')
  }

  const handleClearFace = () => {
    clearFaceDescriptors()
    setHasRegistered(false)
    setAuthState('idle')
    setMessage('')
  }

  const securityLayers = [
    { label: 'Biometric Auth', active: true },
    { label: 'CSP Headers', active: true },
    { label: 'Rate Limiting', active: true },
    { label: 'Anti-Clickjacking', active: true },
    { label: 'Session Token', active: !!session },
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#000', color: '#fff', fontFamily: 'Comfortaa, sans-serif' }}>

      {/* NAVBAR */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.9)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid #1a1a1a',
        padding: '0 32px', height: '60px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <Link href="/" style={{ color: '#444', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            ← Back
          </Link>
          <span style={{ color: '#222' }}>|</span>
          <span style={{ fontWeight: 600, fontSize: '15px' }}>Face Authentication</span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {securityLayers.map((layer) => (
            <div
              key={layer.label}
              title={layer.label}
              style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                padding: '4px 10px',
                background: '#0a0a0a',
                border: '1px solid #1a1a1a',
                borderRadius: '20px',
                fontSize: '10px',
                color: layer.active ? '#22c55e' : '#444',
              }}
            >
              <span style={{
                width: '6px', height: '6px', borderRadius: '50%',
                background: layer.active ? '#22c55e' : '#333',
                flexShrink: 0,
              }} />
              <span className="hidden md:inline">{layer.label}</span>
            </div>
          ))}
        </div>
      </nav>

      <div style={{ maxWidth: '520px', margin: '0 auto', padding: '48px 24px' }}>

        {/* Logged-in state */}
        {session ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '48px', marginBottom: '20px' }}>✅</div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>Authenticated</h1>
            <p style={{ color: '#555', fontSize: '13px', marginBottom: '32px' }}>
              Logged in as <span style={{ color: '#aaa' }}>{session.faceName}</span>.
              Session expires in 1 hour.
            </p>

            <div className="card" style={{ marginBottom: '24px', textAlign: 'left' }}>
              <p style={{ fontSize: '11px', color: '#444', fontWeight: 600, marginBottom: '12px', letterSpacing: '1px', textTransform: 'uppercase' }}>
                Session Info
              </p>
              {[
                ['Token', session.token.slice(0, 16) + '…'],
                ['User', session.faceName],
                ['Expires', new Date(session.expiresAt).toLocaleTimeString()],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #111', fontSize: '13px' }}>
                  <span style={{ color: '#555' }}>{k}</span>
                  <span style={{ color: '#aaa', fontFamily: 'monospace' }}>{v}</span>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
              <Link href="/">
                <button className="btn-white" style={{ fontSize: '13px' }}>Go to Projects</button>
              </Link>
              <button onClick={handleLogout} className="btn-gray" style={{ fontSize: '13px' }}>
                Log Out
              </button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: '32px' }}>
              <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>
                {mode === 'login' ? 'Sign In' : 'Register Face'}
              </h1>
              <p style={{ color: '#555', fontSize: '13px', lineHeight: 1.6 }}>
                {mode === 'login'
                  ? 'Look directly at the camera. Your face is the key.'
                  : 'Register your face once. No password required.'}
              </p>
            </div>

            {/* Mode tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1a1a1a', marginBottom: '32px' }}>
              {['login', 'register'].map((m) => (
                <button
                  key={m}
                  className={`tab ${mode === m ? 'active' : ''}`}
                  onClick={() => { setMode(m); setAuthState('idle'); setMessage('') }}
                >
                  {m === 'login' ? 'Sign In' : 'Register'}
                </button>
              ))}
            </div>

            {/* Message */}
            {message && (
              <div style={{
                background: authState === 'success' ? '#0a1a0a' : '#1a0a0a',
                border: `1px solid ${authState === 'success' ? '#1a3a1a' : '#3a1a1a'}`,
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '20px',
                fontSize: '13px',
                color: authState === 'success' ? '#22c55e' : '#ef4444',
              }}>
                {message}
              </div>
            )}

            {/* Not registered warning in login mode */}
            {mode === 'login' && !hasRegistered && (
              <div style={{
                background: '#111',
                border: '1px solid #222',
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '20px',
                fontSize: '13px',
                color: '#666',
              }}>
                No face registered yet.{' '}
                <button
                  onClick={() => setMode('register')}
                  style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'Comfortaa', fontSize: '13px' }}
                >
                  Register first →
                </button>
              </div>
            )}

            {/* Face recognition component */}
            <FaceRecognition
              key={mode}
              mode={mode}
              onSuccess={handleSuccess}
              onError={handleError}
            />

            {/* Clear registration option */}
            {hasRegistered && (
              <div style={{ marginTop: '24px', textAlign: 'center' }}>
                <button
                  onClick={handleClearFace}
                  style={{ background: 'none', border: 'none', color: '#333', cursor: 'pointer', fontSize: '12px', fontFamily: 'Comfortaa' }}
                >
                  Clear registered face data
                </button>
              </div>
            )}
          </>
        )}

        {/* Security footer */}
        <div style={{ marginTop: '48px', padding: '20px', background: '#080808', borderRadius: '12px', border: '1px solid #111' }}>
          <p style={{ fontSize: '11px', color: '#333', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' }}>
            Security Layers Active
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {securityLayers.map((layer, i) => (
              <div key={layer.label} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '10px', color: '#222', minWidth: '20px' }}>0{i + 1}</span>
                <span style={{
                  width: '6px', height: '6px', borderRadius: '50%',
                  background: layer.active ? '#22c55e' : '#2a2a2a',
                  boxShadow: layer.active ? '0 0 6px #22c55e66' : 'none',
                  flexShrink: 0,
                }} />
                <span style={{ fontSize: '12px', color: layer.active ? '#666' : '#2a2a2a' }}>{layer.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
