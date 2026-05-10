'use client'

import { useRef, useEffect, useState, useCallback } from 'react'
import {
  checkRateLimit,
  recordFailedAttempt,
  storeFaceDescriptor,
  getFaceDescriptors,
  hasFaceRegistered,
  faceDistance,
  FACE_THRESHOLD,
} from '../lib/security'

const MODEL_URL = '/models'

export default function FaceRecognition({ mode = 'login', onSuccess, onError }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const detectionRef = useRef(null)
  const faceapiRef = useRef(null)

  const [phase, setPhase] = useState('loading') // loading | ready | capturing | processing | done | error
  const [statusMsg, setStatusMsg] = useState('Loading AI models...')
  const [faceVisible, setFaceVisible] = useState(false)
  const [confidence, setConfidence] = useState(0)
  const [progress, setProgress] = useState(0)
  const [samplesCollected, setSamplesCollected] = useState(0)
  const SAMPLES_NEEDED = 8

  const descriptorSamples = useRef([])

  // Load face-api.js and models
  useEffect(() => {
    let cancelled = false

    const init = async () => {
      try {
        setStatusMsg('Loading face-api.js...')
        const faceapi = await import('face-api.js')
        faceapiRef.current = faceapi

        // Force CPU backend (WebGL not available in all environments)
        try {
          const tf = faceapi.tf
          await tf.setBackend('cpu')
          await tf.ready()
        } catch (e) {
          console.warn('Backend setup:', e.message)
        }

        setStatusMsg('Loading face detection model...')
        await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL)
        setProgress(33)

        setStatusMsg('Loading landmark model...')
        await faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL)
        setProgress(66)

        setStatusMsg('Loading recognition model...')
        await faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
        setProgress(100)

        if (cancelled) return

        setStatusMsg('Starting camera...')
        await startCamera()

        if (cancelled) return
        setPhase('ready')
        setStatusMsg(
          mode === 'register'
            ? 'Position your face in the frame, then click Register.'
            : 'Position your face in the frame, then click Authenticate.'
        )
      } catch (err) {
        if (!cancelled) {
          setPhase('error')
          setStatusMsg('Error: ' + (err.message || 'Failed to load models'))
          onError && onError(err.message)
        }
      }
    }

    init()
    return () => {
      cancelled = true
      stopAll()
    }
  }, [mode])

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      startDetectionLoop()
    } catch (err) {
      throw new Error('Camera access denied. Please allow camera access to use face authentication.')
    }
  }

  const startDetectionLoop = () => {
    if (detectionRef.current) clearInterval(detectionRef.current)
    detectionRef.current = setInterval(async () => {
      await detectFace()
    }, 200)
  }

  const detectFace = async () => {
    const faceapi = faceapiRef.current
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!faceapi || !video || !canvas || video.readyState < 2) return

    try {
      const detection = await faceapi
        .detectSingleFace(video, new faceapi.TinyFaceDetectorOptions({ scoreThreshold: 0.5 }))
        .withFaceLandmarks()

      const dims = { width: video.videoWidth, height: video.videoHeight }
      canvas.width = dims.width
      canvas.height = dims.height
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      if (detection) {
        setFaceVisible(true)
        const score = Math.round(detection.detection.score * 100)
        setConfidence(score)

        // Draw face box
        const box = detection.detection.box
        ctx.strokeStyle = '#22c55e'
        ctx.lineWidth = 2
        ctx.strokeRect(box.x, box.y, box.width, box.height)

        // Draw corner accents
        const c = 14
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 3
        ;[[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]].forEach(([x, y], i) => {
          ctx.beginPath()
          const dx = i % 2 === 0 ? 1 : -1
          const dy = i < 2 ? 1 : -1
          ctx.moveTo(x, y)
          ctx.lineTo(x + dx * c, y)
          ctx.moveTo(x, y)
          ctx.lineTo(x, y + dy * c)
          ctx.stroke()
        })

        // Confidence label
        ctx.fillStyle = 'rgba(0,0,0,0.7)'
        ctx.fillRect(box.x, box.y - 24, 90, 22)
        ctx.fillStyle = '#22c55e'
        ctx.font = '13px Comfortaa, sans-serif'
        ctx.fillText(`${score}% conf.`, box.x + 4, box.y - 7)
      } else {
        setFaceVisible(false)
        setConfidence(0)
      }
    } catch {
      // Ignore detection errors
    }
  }

  const stopAll = () => {
    if (detectionRef.current) clearInterval(detectionRef.current)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  // Capture multiple descriptor samples for robustness
  const captureDescriptors = useCallback(async () => {
    const faceapi = faceapiRef.current
    const video = videoRef.current
    if (!faceapi || !video) return null

    const samples = []
    for (let i = 0; i < SAMPLES_NEEDED; i++) {
      setSamplesCollected(i)
      await new Promise((r) => setTimeout(r, 150))
      try {
        const det = await faceapi
          .detectSingleFace(video, new faceapi.TinyFaceDetectorOptions({ scoreThreshold: 0.5 }))
          .withFaceLandmarks()
          .withFaceDescriptor()
        if (det) samples.push(Array.from(det.descriptor))
      } catch { /* ignore */ }
    }
    setSamplesCollected(SAMPLES_NEEDED)
    return samples
  }, [])

  const handleRegister = async () => {
    if (!faceVisible) {
      setStatusMsg('No face detected. Make sure your face is clearly visible.')
      return
    }
    setPhase('capturing')
    setStatusMsg('Hold still — capturing face data...')

    const samples = await captureDescriptors()
    if (!samples || samples.length < 3) {
      setPhase('ready')
      setStatusMsg('Could not capture enough samples. Please try again.')
      return
    }

    // Average the descriptors for a more stable representation
    const avgDescriptor = samples[0].map((_, i) =>
      samples.reduce((sum, s) => sum + s[i], 0) / samples.length
    )

    storeFaceDescriptor(avgDescriptor, 'owner')
    setPhase('done')
    setStatusMsg('Face registered successfully!')
    stopAll()
    onSuccess && onSuccess('owner')
  }

  const handleLogin = async () => {
    // Rate limiting check (Layer 3)
    const rateCheck = checkRateLimit()
    if (!rateCheck.allowed) {
      const msg = rateCheck.reason === 'cooldown'
        ? `Too many attempts. Wait ${rateCheck.cooldownSeconds}s before trying again.`
        : 'Maximum login attempts reached. Please wait 15 minutes.'
      setStatusMsg(msg)
      onError && onError(msg)
      return
    }

    if (!faceVisible) {
      setStatusMsg('No face detected. Make sure your face is clearly visible.')
      return
    }

    if (!hasFaceRegistered()) {
      setStatusMsg('No face registered. Please register first.')
      return
    }

    setPhase('capturing')
    setStatusMsg('Verifying identity...')

    const samples = await captureDescriptors()
    if (!samples || samples.length < 2) {
      setPhase('ready')
      recordFailedAttempt()
      setStatusMsg('Could not read face. Try again.')
      return
    }

    const stored = getFaceDescriptors()
    const storedEntries = Object.entries(stored)

    // Compare each sample against stored descriptors
    let bestMatch = null
    let bestDistance = Infinity

    for (const sample of samples) {
      for (const [label, data] of storedEntries) {
        const dist = faceDistance(sample, data.descriptor)
        if (dist < bestDistance) {
          bestDistance = dist
          bestMatch = label
        }
      }
    }

    setPhase('processing')
    await new Promise((r) => setTimeout(r, 500)) // Brief pause for UX

    if (bestDistance < FACE_THRESHOLD) {
      setPhase('done')
      setStatusMsg(`Identity verified. Welcome, ${bestMatch}!`)
      stopAll()
      onSuccess && onSuccess(bestMatch, bestDistance)
    } else {
      setPhase('ready')
      recordFailedAttempt()
      const check = checkRateLimit()
      setStatusMsg(
        `Face not recognized (distance: ${bestDistance.toFixed(3)}). ${check.attemptsLeft} attempts remaining.`
      )
      onError && onError('face_mismatch')
    }
  }

  const getBoxColor = () => {
    if (phase === 'done') return '#22c55e'
    if (phase === 'error') return '#ef4444'
    if (!faceVisible) return '#333'
    return '#22c55e'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', width: '100%' }}>

      {/* Video feed */}
      <div
        className="face-video-container"
        style={{
          width: '100%',
          maxWidth: '480px',
          aspectRatio: '4/3',
          border: `2px solid ${getBoxColor()}`,
          borderRadius: '12px',
          overflow: 'hidden',
          position: 'relative',
          background: '#050505',
        }}
      >
        <video
          ref={videoRef}
          muted
          playsInline
          style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scaleX(-1)' }}
        />
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute',
            top: 0, left: 0,
            width: '100%', height: '100%',
            transform: 'scaleX(-1)',
            pointerEvents: 'none',
          }}
        />

        {/* Loading overlay */}
        {phase === 'loading' && (
          <div style={{
            position: 'absolute', inset: 0,
            background: '#000',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '16px',
          }}>
            <div style={{ fontSize: '32px' }}>🧠</div>
            <p style={{ fontSize: '13px', color: '#666' }}>Loading AI models</p>
            <div style={{ width: '160px', height: '3px', background: '#111', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: '#fff', transition: 'width 0.4s ease', borderRadius: '2px' }} />
            </div>
            <p style={{ fontSize: '11px', color: '#333' }}>{progress}%</p>
          </div>
        )}

        {/* Done overlay */}
        {phase === 'done' && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '12px',
          }}>
            <div style={{ fontSize: '40px' }}>✅</div>
            <p style={{ fontSize: '14px', color: '#22c55e', fontWeight: 600 }}>
              {mode === 'register' ? 'Registered!' : 'Authenticated!'}
            </p>
          </div>
        )}

        {/* Capturing overlay */}
        {(phase === 'capturing' || phase === 'processing') && (
          <div style={{
            position: 'absolute', bottom: '12px', left: '50%', transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.75)',
            padding: '6px 14px',
            borderRadius: '20px',
            fontSize: '12px',
            color: '#fff',
          }}>
            Sampling {samplesCollected}/{SAMPLES_NEEDED}...
          </div>
        )}

        {/* Face status indicator */}
        {phase === 'ready' && (
          <div style={{
            position: 'absolute', top: '12px', right: '12px',
            display: 'flex', alignItems: 'center', gap: '6px',
            background: 'rgba(0,0,0,0.7)',
            padding: '5px 10px',
            borderRadius: '20px',
            fontSize: '11px',
          }}>
            <span
              className="status-dot"
              style={{ background: faceVisible ? '#22c55e' : '#555', boxShadow: faceVisible ? '0 0 6px #22c55e88' : 'none' }}
            />
            <span style={{ color: faceVisible ? '#22c55e' : '#555' }}>
              {faceVisible ? `Face detected` : 'No face'}
            </span>
          </div>
        )}
      </div>

      {/* Status message */}
      <p style={{ fontSize: '13px', color: '#666', textAlign: 'center', maxWidth: '380px', lineHeight: 1.6 }}>
        {statusMsg}
      </p>

      {/* Action button */}
      {phase === 'ready' && (
        mode === 'register' ? (
          <button
            onClick={handleRegister}
            disabled={!faceVisible}
            className="btn-white"
            style={{ padding: '12px 32px', fontSize: '14px', opacity: faceVisible ? 1 : 0.4 }}
          >
            Register My Face
          </button>
        ) : (
          <button
            onClick={handleLogin}
            disabled={!faceVisible}
            className="btn-white"
            style={{ padding: '12px 32px', fontSize: '14px', opacity: faceVisible ? 1 : 0.4 }}
          >
            Authenticate
          </button>
        )
      )}

      {phase === 'error' && (
        <button onClick={() => window.location.reload()} className="btn-gray" style={{ fontSize: '13px' }}>
          Retry
        </button>
      )}
    </div>
  )
}
