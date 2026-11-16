export type MeUser = {
  id: string
  name: string
  role: string
  brands: string[]
}

export type MeResponse = {
  ok?: boolean
  signed_in: boolean
  shared: boolean
  user: MeUser | null
}

let cachedName: string | null = null

export function setMeFromApi(data: MeResponse): void {
  if (data.signed_in && data.user?.name) {
    cachedName = data.user.name
  } else {
    cachedName = null
  }
}

export function signedInActorName(): string | null {
  return cachedName
}

/** Load /api/me once at app start so actorName() knows who is signed in. */
export async function loadMe(): Promise<MeResponse | null> {
  try {
    const res = await fetch('/api/me', { credentials: 'same-origin' })
    if (!res.ok) {
      setMeFromApi({ signed_in: false, shared: false, user: null })
      return null
    }
    const data = (await res.json()) as MeResponse
    setMeFromApi(data)
    return data
  } catch {
    setMeFromApi({ signed_in: false, shared: false, user: null })
    return null
  }
}
