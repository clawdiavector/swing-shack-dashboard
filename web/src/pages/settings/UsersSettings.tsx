import { useCallback, useEffect, useState } from 'react'
import { PageIntro } from '../../components/chrome'
import { fetchBrands } from '../../lib/api'
import { loadMe, type MeUser } from '../../lib/me'

type CosUser = MeUser & {
  email: string
  disabled?: boolean
  created_at?: string
}

const ROLES = ['admin', 'editor', 'approver', 'contributor'] as const

async function usersGet(): Promise<CosUser[]> {
  const r = await fetch('/api/users', { credentials: 'same-origin' })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'Could not load people')
  return j.users as CosUser[]
}

async function usersPost(body: Record<string, unknown>): Promise<void> {
  const r = await fetch('/api/users', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'Could not add person')
}

async function usersPatch(id: string, body: Record<string, unknown>): Promise<void> {
  const r = await fetch(`/api/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'Could not save changes')
}

function OwnPassword() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

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
      setMsg('Password changed. Use the new one next time you sign in.')
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Could not change password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-tx3">Your password</h2>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit}>
        <label className="block text-xs text-tx2 sm:col-span-2">
          Current password
          <input type="password" className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
        </label>
        <label className="block text-xs text-tx2">
          New password
          <input type="password" className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={next} onChange={(e) => setNext(e.target.value)} required autoComplete="new-password" />
        </label>
        <label className="block text-xs text-tx2">
          New password again
          <input type="password" className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={again} onChange={(e) => setAgain(e.target.value)} required autoComplete="new-password" />
        </label>
        <div className="sm:col-span-2">
          <button type="submit" disabled={busy} className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50">
            Change password
          </button>
        </div>
      </form>
      {err ? <p className="text-sm text-red">{err}</p> : null}
      {msg ? <p className="text-sm text-tx">{msg}</p> : null}
    </section>
  )
}

async function usersPassword(id: string, password: string): Promise<void> {
  const r = await fetch(`/api/users/${encodeURIComponent(id)}/password`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'Could not reset password')
}

export function UsersSettings() {
  const [me, setMe] = useState<MeUser | null>(null)
  const [users, setUsers] = useState<CosUser[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<(typeof ROLES)[number]>('contributor')
  const [password, setPassword] = useState('')
  const [brandPick, setBrandPick] = useState<string[]>(['*'])

  const reload = useCallback(async () => {
    setErr('')
    const profile = await loadMe()
    setMe(profile?.user ?? null)
    try {
      const [rows, brandRes] = await Promise.all([usersGet(), fetchBrands()])
      setUsers(rows)
      setBrands(Object.keys(brandRes.brands || {}))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not load people')
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  async function addUser(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      await usersPost({
        name,
        email,
        role,
        password,
        brands: brandPick.length ? brandPick : ['*'],
      })
      setName('')
      setEmail('')
      setPassword('')
      await reload()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Could not add person')
    } finally {
      setBusy(false)
    }
  }

  async function toggleBrand(id: string, bid: string, on: boolean, current: string[]) {
    const next = on ? [...new Set([...current, bid])] : current.filter((b) => b !== bid)
    try {
      await usersPatch(id, { brands: next.length ? next : ['*'] })
      await reload()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Could not save brands')
    }
  }

  if (me && me.role !== 'admin') {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <PageIntro here="/settings/users" title="Logins">
          Change your own password here.
        </PageIntro>
        <OwnPassword />
        <p className="text-sm text-tx2">Adding people, and resetting someone else's password, stays with Kyle.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6">
      <PageIntro here="/settings/users" title="Logins">
        Named accounts for Campaign OS. The shared password still works until everyone has their own login.
      </PageIntro>
      {err ? <p className="rounded-lg border border-red/40 bg-red/10 px-3 py-2 text-sm text-red">{err}</p> : null}

      {me ? <OwnPassword /> : null}

      <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-tx3">Add someone</h2>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={addUser}>
          <label className="block text-xs text-tx2">
            Name
            <input className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="block text-xs text-tx2">
            Email
            <input type="email" className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label className="block text-xs text-tx2">
            Role
            <select className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={role} onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-tx2">
            Starting password
            <input type="password" className="mt-1 w-full rounded-lg border border-white/10 bg-bg2 px-3 py-2 text-sm" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <fieldset className="sm:col-span-2">
            <legend className="text-xs text-tx2">Brands</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              <label className="text-xs">
                <input type="checkbox" checked={brandPick.includes('*')} onChange={(e) => setBrandPick(e.target.checked ? ['*'] : [])} /> All brands
              </label>
              {brands.map((b) => (
                <label key={b} className="text-xs">
                  <input
                    type="checkbox"
                    disabled={brandPick.includes('*')}
                    checked={brandPick.includes(b)}
                    onChange={(e) =>
                      setBrandPick((prev) => {
                        const base = prev.filter((x) => x !== '*')
                        return e.target.checked ? [...base, b] : base.filter((x) => x !== b)
                      })
                    }
                  />{' '}
                  {b}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
            >
              Add login
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-tx3">People</h2>
        <ul className="space-y-3">
          {users.map((u) => (
            <li key={u.id} className="glass rounded-2xl border border-white/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-semibold">{u.name}</p>
                  <p className="text-xs text-tx2">{u.email}</p>
                </div>
                <select
                  className="rounded-lg border border-white/10 bg-bg2 px-2 py-1 text-xs"
                  value={u.role}
                  onChange={async (e) => {
                    try {
                      await usersPatch(u.id, { role: e.target.value })
                      await reload()
                    } catch (ex) {
                      setErr(ex instanceof Error ? ex.message : 'Could not save role')
                    }
                  }}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {(u.brands || []).map((b) => (
                  <span key={b} className="rounded-full bg-white/10 px-2 py-0.5">
                    {b}
                  </span>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="glass-pill rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-tx"
                  onClick={async () => {
                    const pw = window.prompt('New password for this person')
                    if (!pw) return
                    try {
                      await usersPassword(u.id, pw)
                    } catch (ex) {
                      setErr(ex instanceof Error ? ex.message : 'Could not reset password')
                    }
                  }}
                >
                  Reset password
                </button>
                <button
                  type="button"
                  className="glass-pill rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-tx"
                  onClick={async () => {
                    try {
                      await usersPatch(u.id, { disabled: !u.disabled })
                      await reload()
                    } catch (ex) {
                      setErr(ex instanceof Error ? ex.message : 'Could not update')
                    }
                  }}
                >
                  {u.disabled ? 'Enable' : 'Disable'}
                </button>
              </div>
              {brands.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-tx2">
                  {brands.map((b) => (
                    <label key={`${u.id}-${b}`}>
                      <input
                        type="checkbox"
                        checked={(u.brands || []).includes(b) || (u.brands || []).includes('*')}
                        disabled={(u.brands || []).includes('*')}
                        onChange={(e) => void toggleBrand(u.id, b, e.target.checked, u.brands || [])}
                      />{' '}
                      {b}
                    </label>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
