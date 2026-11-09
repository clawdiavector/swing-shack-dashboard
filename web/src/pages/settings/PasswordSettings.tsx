import { useEffect, useState } from 'react'
import { PageIntro } from '../../components/chrome'
import { loadMe } from '../../lib/me'

export function PasswordSettings() {
  const [named, setNamed] = useState<boolean | null>(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void loadMe().then((profile) => setNamed(Boolean(profile?.user)))
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    setMsg('')
    if (next !== again) {
      setErr('The new password was typed differently the second time.')
      return
    }
    setBusy(true)
    try {
      const r = await fetch('/api/me/password', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current, password: next }),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.error || 'Could not change password')
      setCurrent('')
      setNext('')
      setAgain('')
      setMsg('Password changed. Use the new one next time you sign in. This browser stays signed in.')
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Could not change password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 p-6">
      <PageIntro here="/settings/password" title="Password">
        Change the password for the person who is signed in. This does not change anyone else's.
      </PageIntro>
      {named === false ? (
        <p className="text-sm text-tx2">
          Sign in with your email to change a password. The shared team password has nothing of its own to change.
        </p>
      ) : (
        <form className="glass space-y-3 rounded-2xl border border-white/10 p-4" onSubmit={submit}>
          <label className="block text-xs text-tx2">
            Current password
            <input
              type="password"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <label className="block text-xs text-tx2">
            New password
            <input
              type="password"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
          <label className="block text-xs text-tx2">
            New password again
            <input
              type="password"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
          <button
            type="submit"
            disabled={busy || named === null}
            className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
          >
            Change password
          </button>
          {err ? <p className="text-sm text-red">{err}</p> : null}
          {msg ? <p className="text-sm text-tx">{msg}</p> : null}
        </form>
      )}
    </div>
  )
}
