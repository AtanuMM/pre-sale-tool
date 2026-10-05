import { EyeIcon, EyeOffIcon, Loader2Icon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import { useAuth } from '@/auth/AuthContext'
import { ThemeToggleButton } from '@/components/layout/ThemeToggleButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const WORKFLOW_PREVIEW = [
  'Scope analysis',
  'Gap analysis',
  'Feature list',
  'Estimate',
  'SOW',
  'SRS',
  'Sprint plan',
  'FRS',
] as const

export function LoginPage() {
  useDocumentTitle('Sign in')
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from =
    (location.state as { from?: string } | null)?.from && typeof location.state === 'object'
      ? (location.state as { from?: string }).from
      : '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(from ?? '/', { replace: true })
    } catch (err) {
      const message =
        err instanceof ApiError ? err.displayMessage() : 'Sign-in failed. Please try again.'
      setError(message)
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative grid min-h-svh lg:grid-cols-2">
      <div className="absolute right-4 top-4 z-10">
        <ThemeToggleButton />
      </div>

      <div className="flex flex-col justify-center px-6 py-12 sm:px-10 lg:px-16">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground shadow-xs">
              S
            </div>
            <span className="text-lg font-semibold tracking-tight">ScopeDesk</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Sign in</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Use your company email and password.
          </p>
          <form className="mt-8 space-y-4" onSubmit={(e) => void handleSubmit(e)} noValidate>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  className="pr-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="absolute top-1/2 right-1 -translate-y-1/2 text-muted-foreground"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                </Button>
              </div>
            </div>
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting && <Loader2Icon className="size-4 animate-spin" />}
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </div>
      </div>

      <div className="login-brand-panel relative hidden overflow-hidden bg-primary lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="relative z-10 flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-primary-foreground/15 text-lg font-bold text-primary-foreground backdrop-blur-sm">
            S
          </div>
          <span className="text-2xl font-semibold tracking-tight text-primary-foreground">
            ScopeDesk
          </span>
        </div>
        <div className="relative z-10 max-w-md space-y-4">
          <p className="text-lg font-medium leading-snug text-primary-foreground">
            Scope analysis, structured workflow steps, and delivery documentation in one place.
          </p>
          <div className="login-workflow-preview rounded-xl border border-primary-foreground/20 bg-primary-foreground/10 p-5 backdrop-blur-sm">
            <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-primary-foreground/80">
              Workflow pipeline
            </p>
            <ol className="login-workflow-steps">
              {WORKFLOW_PREVIEW.map((step, i) => (
                <li key={step}>
                  <span className="login-workflow-step-index">{i + 1}</span>
                  <span className="login-workflow-step-label">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <p className="relative z-10 text-sm text-primary-foreground/70">Matrix Media Solutions</p>
      </div>
    </div>
  )
}
