import type { FormEvent } from 'react'
import type { AuthMode } from '../types/auth'

interface AuthFormProps {
  mode: AuthMode
  setMode: (mode: AuthMode) => void
  email: string
  setEmail: (value: string) => void
  password: string
  setPassword: (value: string) => void
  loading: boolean
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function AuthForm({
  mode,
  setMode,
  email,
  setEmail,
  password,
  setPassword,
  loading,
  onSubmit,
}: AuthFormProps) {
  return (
    <>
      <div className="mode-switch" role="tablist" aria-label="Authentication mode">
        <button
          type="button"
          className={mode === 'login' ? 'mode-switch__btn active' : 'mode-switch__btn'}
          onClick={() => setMode('login')}
        >
          Login
        </button>
        <button
          type="button"
          className={mode === 'signup' ? 'mode-switch__btn active' : 'mode-switch__btn'}
          onClick={() => setMode('signup')}
        >
          Sign up
        </button>
      </div>

      <form className="auth-form" onSubmit={onSubmit}>
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter your password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
        </label>

        <button type="submit" className="primary-btn" disabled={loading}>
          {loading ? 'Please wait…' : mode === 'login' ? 'Login' : 'Create account'}
        </button>
      </form>
    </>
  )
}
