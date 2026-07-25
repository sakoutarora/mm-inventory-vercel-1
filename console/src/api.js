const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://dqrul4dok9.execute-api.ap-south-1.amazonaws.com/prod/api/v1').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    method: options.method || 'GET',
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.message || `Request failed (${response.status})`)
  }
  return payload
}

export const api = {
  login: (body) => request('/auth/login', { method: 'POST', body }),
  getInventoryItems: (branchCode, token) =>
    request(`/inventory/items?branchCode=${encodeURIComponent(branchCode)}`, { token }),
  submitInventoryUpdate: (body, token) =>
    request('/inventory/update', { method: 'POST', body, token }),
  getDashboardSummary: (branchCode, token, days = 14) =>
    request(`/dashboard/summary?branchCode=${encodeURIComponent(branchCode)}&days=${days}`, { token }),
  getAdminMeta: (token) => request('/admin/meta', { token }),
  createCategory: (body, token) => request('/admin/categories', { method: 'POST', body, token }),
  createItem: (body, token) => request('/admin/items', { method: 'POST', body, token }),
  updateItem: (body, token) => request('/admin/items', { method: 'PATCH', body, token }),
  createUser: (body, token) => request('/admin/users', { method: 'POST', body, token }),
}
