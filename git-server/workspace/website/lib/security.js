// Security utility functions

const RATE_LIMIT_KEY = 'cft_rate_limit'
const SESSION_KEY = 'cft_session'
const MAX_ATTEMPTS = 5
const WINDOW_MS = 15 * 60 * 1000 // 15 minutes
const COOLDOWN_MS = 60 * 1000 // 60 seconds
const SESSION_DURATION = 60 * 60 * 1000 // 1 hour

// --- Rate limiting (Layer 3) ---
export function checkRateLimit() {
  if (typeof window === 'undefined') return { allowed: true, attemptsLeft: MAX_ATTEMPTS }
  const raw = localStorage.getItem(RATE_LIMIT_KEY)
  const now = Date.now()

  if (!raw) return { allowed: true, attemptsLeft: MAX_ATTEMPTS }

  const data = JSON.parse(raw)

  // Reset window if expired
  if (now - data.windowStart > WINDOW_MS) {
    localStorage.removeItem(RATE_LIMIT_KEY)
    return { allowed: true, attemptsLeft: MAX_ATTEMPTS }
  }

  // Check cooldown
  if (data.cooldownUntil && now < data.cooldownUntil) {
    const remaining = Math.ceil((data.cooldownUntil - now) / 1000)
    return { allowed: false, attemptsLeft: 0, cooldownSeconds: remaining, reason: 'cooldown' }
  }

  if (data.attempts >= MAX_ATTEMPTS) {
    return { allowed: false, attemptsLeft: 0, reason: 'max_attempts' }
  }

  return { allowed: true, attemptsLeft: MAX_ATTEMPTS - data.attempts }
}

export function recordFailedAttempt() {
  if (typeof window === 'undefined') return
  const now = Date.now()
  const raw = localStorage.getItem(RATE_LIMIT_KEY)
  let data = raw ? JSON.parse(raw) : { attempts: 0, windowStart: now }

  if (now - data.windowStart > WINDOW_MS) {
    data = { attempts: 0, windowStart: now }
  }

  data.attempts += 1

  // Apply cooldown after 3+ failures
  if (data.attempts >= 3) {
    data.cooldownUntil = now + COOLDOWN_MS
  }

  localStorage.setItem(RATE_LIMIT_KEY, JSON.stringify(data))
}

export function resetRateLimit() {
  if (typeof window === 'undefined') return
  localStorage.removeItem(RATE_LIMIT_KEY)
}

// --- Session management (Layer 5) ---
function generateToken() {
  const arr = new Uint8Array(32)
  crypto.getRandomValues(arr)
  return Array.from(arr, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function createSession(faceName) {
  if (typeof window === 'undefined') return null
  const token = generateToken()
  const session = {
    token,
    faceName: faceName || 'user',
    createdAt: Date.now(),
    expiresAt: Date.now() + SESSION_DURATION,
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
  resetRateLimit()
  return session
}

export function getSession() {
  if (typeof window === 'undefined') return null
  const raw = sessionStorage.getItem(SESSION_KEY)
  if (!raw) return null
  const session = JSON.parse(raw)
  if (Date.now() > session.expiresAt) {
    sessionStorage.removeItem(SESSION_KEY)
    return null
  }
  return session
}

export function clearSession() {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(SESSION_KEY)
}

// --- Input sanitization ---
export function sanitizeInput(str) {
  if (typeof str !== 'string') return ''
  return str
    .replace(/[<>'"&]/g, '')
    .replace(/javascript:/gi, '')
    .replace(/on\w+=/gi, '')
    .trim()
    .slice(0, 200)
}

// --- Face descriptor storage ---
const FACE_STORE_KEY = 'cft_face_descriptors'

export function storeFaceDescriptor(descriptor, label = 'owner') {
  if (typeof window === 'undefined') return
  const existing = getFaceDescriptors()
  const arr = descriptor instanceof Float32Array ? Array.from(descriptor) : descriptor
  existing[label] = { descriptor: arr, registeredAt: Date.now() }
  localStorage.setItem(FACE_STORE_KEY, JSON.stringify(existing))
}

export function getFaceDescriptors() {
  if (typeof window === 'undefined') return {}
  const raw = localStorage.getItem(FACE_STORE_KEY)
  return raw ? JSON.parse(raw) : {}
}

export function clearFaceDescriptors() {
  if (typeof window === 'undefined') return
  localStorage.removeItem(FACE_STORE_KEY)
}

export function hasFaceRegistered() {
  const descriptors = getFaceDescriptors()
  return Object.keys(descriptors).length > 0
}

// --- Euclidean distance for face comparison ---
export function faceDistance(desc1, desc2) {
  if (desc1.length !== desc2.length) return Infinity
  let sum = 0
  for (let i = 0; i < desc1.length; i++) {
    const diff = desc1[i] - desc2[i]
    sum += diff * diff
  }
  return Math.sqrt(sum)
}

export const FACE_THRESHOLD = 0.55 // strict threshold
