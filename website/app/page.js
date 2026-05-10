'use client'

import { useState } from 'react'
import Link from 'next/link'

const projects = [
  {
    id: 1,
    name: 'Fredbear Animatronic System',
    version: 'v3.1.0',
    status: 'active',
    lang: 'Python',
    description: 'Complete animatronic control system for Fredbear. Features 7-axis facial expression, AI brain with GPT-4o, lip-sync TTS, and WebSocket remote control.',
    tags: ['AI', 'Robotics', 'Computer Vision', 'TTS'],
    stats: { modules: 14, tests: 48, lines: '6.2k' },
  },
  {
    id: 2,
    name: 'Springbonnie Animatronic System',
    version: 'v3.1.0',
    status: 'active',
    lang: 'Python',
    description: 'Animatronic system for Springbonnie. Shares the modular core architecture with Fredbear, with a distinct personality mode set including Creepy, Guardian, and DJ.',
    tags: ['AI', 'Robotics', 'SLAM', 'Locomotion'],
    stats: { modules: 12, tests: 42, lines: '5.8k' },
  },
  {
    id: 3,
    name: 'Cyber Fun Core',
    version: 'v3.1.0',
    status: 'active',
    lang: 'Python',
    description: 'Shared modular core library powering all animatronic characters. Includes HAL, FSM kernel, A* pathfinding, facial controller, and computer vision engine.',
    tags: ['Library', 'HAL', 'FSM', 'A* Pathfinding'],
    stats: { modules: 8, tests: 62, lines: '9.1k' },
  },
  {
    id: 4,
    name: 'Animatronic Simulator',
    version: 'v2.0',
    status: 'stable',
    lang: 'Python',
    description: 'Full simulation mode that runs the entire animatronic system without any physical hardware. Ideal for development, testing, and demonstration.',
    tags: ['Simulation', 'Testing', 'Debug'],
    stats: { modules: 3, tests: 18, lines: '1.4k' },
  },
  {
    id: 5,
    name: 'Face Auth System',
    version: 'v1.0',
    status: 'beta',
    lang: 'Python + JS',
    description: 'Biometric facial recognition authentication system for securing access to the animatronic control dashboard. Uses real-time face descriptor comparison.',
    tags: ['Security', 'Biometrics', 'AI', 'Auth'],
    stats: { modules: 5, tests: 22, lines: '2.1k' },
  },
]

const allTags = ['All', 'AI', 'Robotics', 'Security', 'Simulation', 'Library', 'Computer Vision']

const statusColors = {
  active: '#22c55e',
  stable: '#3b82f6',
  beta: '#f59e0b',
}

export default function Home() {
  const [activeTab, setActiveTab] = useState('projects')
  const [filterTag, setFilterTag] = useState('All')
  const [search, setSearch] = useState('')

  const sanitize = (str) => str.replace(/[<>"']/g, '')

  const filtered = projects.filter((p) => {
    const matchTag = filterTag === 'All' || p.tags.includes(filterTag)
    const q = sanitize(search).toLowerCase()
    const matchSearch =
      !q ||
      p.name.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q) ||
      p.tags.some((t) => t.toLowerCase().includes(q))
    return matchTag && matchSearch
  })

  return (
    <div style={{ minHeight: '100vh', background: '#000', color: '#fff', fontFamily: 'Comfortaa, sans-serif' }}>

      {/* NAVBAR */}
      <nav className="navbar" style={{ padding: '0 32px', height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '20px' }}>⚙️</span>
          <span style={{ fontWeight: 700, fontSize: '16px', letterSpacing: '0.5px' }}>CyberFun Tech</span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <a
            href="https://github.com/V0rtexLinux/cyberfun_tech_v3"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-gray"
            style={{ fontSize: '13px' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            GitHub
          </a>
          <Link href="/auth">
            <button className="btn-white" style={{ fontSize: '13px' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
              </svg>
              Face Login
            </button>
          </Link>
        </div>
      </nav>

      {/* HERO */}
      <div style={{ padding: '64px 32px 40px', maxWidth: '1100px', margin: '0 auto' }}>
        <div style={{ marginBottom: '8px' }}>
          <span className="badge">Open Source</span>
          <span className="badge" style={{ marginLeft: '8px' }}>Python</span>
          <span className="badge" style={{ marginLeft: '8px' }}>Raspberry Pi 4</span>
        </div>
        <h1 style={{ fontSize: 'clamp(28px, 5vw, 48px)', fontWeight: 700, marginTop: '20px', marginBottom: '16px', lineHeight: 1.2 }}>
          CyberFun Tech
        </h1>
        <p style={{ fontSize: '16px', color: '#888', maxWidth: '580px', lineHeight: 1.7, fontWeight: 400 }}>
          Professional animatronic control systems built in Python for Raspberry Pi 4.
          Featuring AI, computer vision, autonomous navigation, and biometric security.
        </p>
      </div>

      <hr className="divider" />

      {/* TABS */}
      <div style={{ padding: '0 32px', maxWidth: '1100px', margin: '0 auto', display: 'flex', gap: '4px', borderBottom: '1px solid #1a1a1a' }}>
        {['projects', 'about', 'security'].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div style={{ padding: '32px', maxWidth: '1100px', margin: '0 auto' }}>

        {/* PROJECTS TAB */}
        {activeTab === 'projects' && (
          <>
            {/* Filters */}
            <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setFilterTag(tag)}
                    className="btn-gray"
                    style={{
                      fontSize: '12px',
                      padding: '6px 14px',
                      borderColor: filterTag === tag ? '#555' : '#222',
                      color: filterTag === tag ? '#fff' : '#666',
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
              <input
                type="text"
                placeholder="Search projects..."
                value={search}
                onChange={(e) => setSearch(sanitize(e.target.value))}
                maxLength={50}
                style={{
                  background: '#0d0d0d',
                  border: '1px solid #222',
                  borderRadius: '8px',
                  padding: '8px 16px',
                  color: '#fff',
                  fontFamily: 'Comfortaa, sans-serif',
                  fontSize: '13px',
                  width: '220px',
                  outline: 'none',
                }}
              />
            </div>

            {/* Project grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
              {filtered.map((project) => (
                <div key={project.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span
                          className="status-dot"
                          style={{ background: statusColors[project.status] }}
                        />
                        <span style={{ fontSize: '11px', color: '#555', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          {project.status}
                        </span>
                      </div>
                      <h3 style={{ fontSize: '15px', fontWeight: 600, lineHeight: 1.3, color: '#fff' }}>
                        {project.name}
                      </h3>
                    </div>
                    <span className="badge" style={{ fontSize: '11px', flexShrink: 0 }}>{project.version}</span>
                  </div>

                  {/* Description */}
                  <p style={{ fontSize: '13px', color: '#666', lineHeight: 1.65, flexGrow: 1 }}>
                    {project.description}
                  </p>

                  {/* Tags */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {project.tags.map((tag) => (
                      <button
                        key={tag}
                        className="badge"
                        onClick={() => setFilterTag(allTags.includes(tag) ? tag : 'All')}
                        style={{ cursor: 'pointer', fontSize: '11px' }}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>

                  {/* Stats */}
                  <div style={{ display: 'flex', gap: '20px', paddingTop: '12px', borderTop: '1px solid #1a1a1a' }}>
                    {[
                      { label: 'Modules', value: project.stats.modules },
                      { label: 'Tests', value: project.stats.tests },
                      { label: 'Lines', value: project.stats.lines },
                    ].map((s) => (
                      <div key={s.label} style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600 }}>{s.value}</div>
                        <div style={{ fontSize: '11px', color: '#555' }}>{s.label}</div>
                      </div>
                    ))}
                    <div style={{ marginLeft: 'auto' }}>
                      <span className="badge" style={{ fontSize: '11px' }}>{project.lang}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {filtered.length === 0 && (
              <div style={{ textAlign: 'center', padding: '80px 0', color: '#444' }}>
                <p style={{ fontSize: '15px' }}>No projects match your search.</p>
              </div>
            )}
          </>
        )}

        {/* ABOUT TAB */}
        {activeTab === 'about' && (
          <div style={{ maxWidth: '720px', lineHeight: 1.8 }}>
            <h2 style={{ fontSize: '22px', fontWeight: 600, marginBottom: '24px' }}>About CyberFun Tech</h2>

            <div className="card" style={{ marginBottom: '16px' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px', color: '#ccc' }}>What is this?</h3>
              <p style={{ fontSize: '14px', color: '#666' }}>
                CyberFun Tech is a professional-grade animatronic control platform built entirely in Python.
                It powers real animatronic characters (Fredbear and Springbonnie) running on Raspberry Pi 4 with
                Arduino Mega 2560 for low-level hardware control.
              </p>
            </div>

            <div className="card" style={{ marginBottom: '16px' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px', color: '#ccc' }}>Hardware Stack</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                {[
                  ['SBC', 'Raspberry Pi 4 (4GB)'],
                  ['MCU', 'Arduino Mega 2560'],
                  ['Servos', '7× MG996R / DS3218'],
                  ['Camera', 'Raspberry Pi Camera v2'],
                  ['IMU', 'MPU-6050 (I2C)'],
                  ['Sensors', 'PIR + HC-SR04 Ultrasonic'],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                    <span style={{ fontSize: '12px', color: '#555', minWidth: '70px', fontWeight: 600 }}>{k}</span>
                    <span style={{ fontSize: '13px', color: '#aaa' }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px', color: '#ccc' }}>License & Source</h3>
              <p style={{ fontSize: '14px', color: '#666', marginBottom: '12px' }}>
                All projects are open source under the MIT License.
              </p>
              <a
                href="https://github.com/V0rtexLinux/cyberfun_tech_v3"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-gray"
                style={{ fontSize: '13px' }}
              >
                View on GitHub →
              </a>
            </div>
          </div>
        )}

        {/* SECURITY TAB */}
        {activeTab === 'security' && (
          <div style={{ maxWidth: '720px' }}>
            <h2 style={{ fontSize: '22px', fontWeight: 600, marginBottom: '8px' }}>Security Architecture</h2>
            <p style={{ fontSize: '14px', color: '#555', marginBottom: '28px' }}>
              5 independent layers protecting this system from unauthorized access.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[
                {
                  layer: '01',
                  name: 'Biometric Face Authentication',
                  desc: 'Real-time face descriptor comparison using TensorFlow.js + face-api.js. 128-dimensional embedding vectors compared with Euclidean distance (threshold < 0.6). No face, no access.',
                  status: 'active',
                },
                {
                  layer: '02',
                  name: 'Content Security Policy (CSP)',
                  desc: 'Strict HTTP Content-Security-Policy headers block unauthorized scripts, external connections, and injection attacks. Only whitelisted origins are allowed.',
                  status: 'active',
                },
                {
                  layer: '03',
                  name: 'Rate Limiting',
                  desc: 'Authentication attempts are limited to 5 per 15-minute window. After 3 failed face matches, a 60-second cooldown is enforced before retry.',
                  status: 'active',
                },
                {
                  layer: '04',
                  name: 'Anti-Clickjacking & MIME Protection',
                  desc: 'X-Frame-Options (SAMEORIGIN), X-Content-Type-Options (nosniff), and X-XSS-Protection headers prevent framing attacks and MIME confusion.',
                  status: 'active',
                },
                {
                  layer: '05',
                  name: 'Session Token with Expiry',
                  desc: 'After successful face auth, a cryptographically-random session token is issued with a 1-hour expiry. All protected routes verify the token on every access.',
                  status: 'active',
                },
              ].map((item) => (
                <div key={item.layer} className="card" style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: '11px', color: '#333', fontWeight: 700, minWidth: '24px', paddingTop: '2px', letterSpacing: '1px' }}>
                    {item.layer}
                  </div>
                  <div style={{ flexGrow: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                      <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#ddd' }}>{item.name}</h3>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: '#22c55e' }}>
                        <span className="status-dot green" />
                        Active
                      </span>
                    </div>
                    <p style={{ fontSize: '13px', color: '#555', lineHeight: 1.65 }}>{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* FOOTER */}
      <footer style={{ borderTop: '1px solid #111', padding: '24px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#333', fontSize: '13px', marginTop: '40px' }}>
        <span>CyberFun Tech © 2025 — MIT License</span>
        <div style={{ display: 'flex', gap: '16px' }}>
          <a href="https://github.com/V0rtexLinux/cyberfun_tech_v3" target="_blank" rel="noopener noreferrer" style={{ color: '#444' }}>
            GitHub
          </a>
          <Link href="/auth" style={{ color: '#444' }}>Face Auth</Link>
        </div>
      </footer>
    </div>
  )
}
