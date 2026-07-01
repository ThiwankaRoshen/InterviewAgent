import './App.css'
import { AuthenticatedState } from './components/AuthenticatedState'
import { AuthForm } from './components/AuthForm'
import { useAuth } from './hooks/useAuth'

function App() {
  const {
    mode,
    setMode,
    email,
    setEmail,
    password,
    setPassword,
    isAuthenticated,
    userEmail,
    loading,
    message,
    feedbackType,
    handleSubmit,
    handleLogout,
  } = useAuth()

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-card__header">
          <p className="eyebrow">InterviewAgent</p>
          <h1>{isAuthenticated ? 'Welcome back' : mode === 'login' ? 'Log in to continue' : 'Create your account'}</h1>
          <p className="auth-card__subtitle">
            {isAuthenticated
              ? 'Your session is active. You can continue to your interview journey.'
              : 'Use this first step to sign in or create a new account for your practice sessions.'}
          </p>
        </div>

        {message ? <div className={`feedback ${feedbackType}`}>{message}</div> : null}

        {isAuthenticated ? (
          <AuthenticatedState userEmail={userEmail} onLogout={handleLogout} />
        ) : (
          <AuthForm
            mode={mode}
            setMode={setMode}
            email={email}
            setEmail={setEmail}
            password={password}
            setPassword={setPassword}
            loading={loading}
            onSubmit={handleSubmit}
          />
        )}
      </section>
    </main>
  )
}

export default App
