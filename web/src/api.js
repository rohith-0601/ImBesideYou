const base = '/api'

async function req(path, opts) {
  const res = await fetch(base + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const body = await res.json()
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
  return body
}

export const listProcesses = () => req('/processes')
export const getQueue = (p) => req(`/processes/${p}/queue`)
export const submit = (p, record_id, comment) =>
  req(`/processes/${p}/submit`, {
    method: 'POST',
    body: JSON.stringify({ record_id, comment }),
  })
