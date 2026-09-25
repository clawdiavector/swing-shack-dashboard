/** Keep first occurrence when parallel brand fan-out returns the same id twice. */
export function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const byId = new Map<string, T>()
  for (const item of items) {
    if (!byId.has(item.id)) {
      byId.set(item.id, item)
    }
  }
  return [...byId.values()]
}
