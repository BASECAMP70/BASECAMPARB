const BASE = 'http://localhost:8000'

export async function fetchOpportunities() {
  const res = await fetch(`${BASE}/api/opportunities`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchBooks() {
  const res = await fetch(`${BASE}/api/books`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
