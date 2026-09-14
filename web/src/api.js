const BASE = '/api'

async function request(path, options) {
  let res
  try {
    res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error('Cannot reach the portal adapter. Is the API running on :8765?')
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`)
  return body
}

export const listProcesses = () => request('/processes')
export const getQueue = (label) => request(`/processes/${label}/queue`)
export const submitBatch = (label, records) =>
  request(`/processes/${label}/submit-batch`, {
    method: 'POST',
    body: JSON.stringify({ records }),
  })

export const submitRecord = (label, record_id, comment) =>
  request(`/processes/${label}/submit`, {
    method: 'POST',
    body: JSON.stringify({ record_id, comment }),
  })
