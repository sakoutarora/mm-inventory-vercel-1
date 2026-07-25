import { useEffect, useMemo, useState } from 'react'
import { api } from './api'

const MODES = [
  { id: 'inventory', label: 'Inventory', hint: 'Daily branch stock entry' },
  { id: 'dashboard', label: 'Dashboard', hint: 'Consumption & risk insights' },
  { id: 'admin', label: 'Admin', hint: 'Master data & users' },
]

const ADMIN_SECTIONS = [
  { id: 'categories', label: 'Categories' },
  { id: 'items', label: 'Items' },
  { id: 'users', label: 'Users' },
]

function App() {
  const [session, setSession] = useState(null)
  const [activeTab, setActiveTab] = useState('inventory')
  const [activeAdminSection, setActiveAdminSection] = useState('categories')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [inventoryItems, setInventoryItems] = useState([])
  const [inventoryEdits, setInventoryEdits] = useState({})
  const [dashboard, setDashboard] = useState(null)
  const [adminMeta, setAdminMeta] = useState({ branches: [], categories: [], items: [], users: [] })

  const [categoryForm, setCategoryForm] = useState({ code: '', name: '', displayOrder: 999 })
  const [newItemForm, setNewItemForm] = useState({
    sku: '',
    name: '',
    categoryCode: '',
    defaultUnit: '',
    allowedUnits: '',
    minThreshold: '',
    isRequired: false,
  })
  const [editItemId, setEditItemId] = useState('')
  const [editItemForm, setEditItemForm] = useState({ minThreshold: '', defaultUnit: '', allowedUnits: '' })
  const [userForm, setUserForm] = useState({ username: '', password: '', fullName: '', role: 'staff', branchCodes: [] })

  const groupedInventory = useMemo(() => {
    const group = {}
    for (const item of inventoryItems) {
      if (!group[item.category]) group[item.category] = []
      group[item.category].push(item)
    }
    return group
  }, [inventoryItems])

  const changedInventoryItems = useMemo(() => {
    return inventoryItems
      .map((item) => {
        const edit = inventoryEdits[item.id] || {}
        const quantity = String(edit.quantity ?? item.lastQuantity ?? '').trim()
        const unit = String(edit.unit ?? item.lastUnit ?? '').trim()
        const changed = quantity !== String(item.lastQuantity ?? '') || unit !== String(item.lastUnit ?? '')
        if (!changed || !quantity || !unit) return null
        return {
          itemId: item.id,
          name: item.name,
          category: item.category,
          quantity,
          unit,
          required: item.required,
        }
      })
      .filter(Boolean)
  }, [inventoryItems, inventoryEdits])

  useEffect(() => {
    if (session?.role === 'admin' && activeTab === 'admin') {
      loadAdminMeta()
    }
  }, [activeTab, session?.role])

  // Auto-dismiss notices after 4s
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(''), 4000)
    return () => clearTimeout(t)
  }, [notice])

  async function loadInventory() {
    if (!session) return
    const data = await api.getInventoryItems(session.branchCode, session.token)
    setInventoryItems(data.items || [])
    setInventoryEdits({})
  }

  async function loadDashboard() {
    if (!session) return
    const data = await api.getDashboardSummary(session.branchCode, session.token, 14)
    setDashboard(data)
  }

  async function loadAdminMeta() {
    if (!session || session.role !== 'admin') return
    const data = await api.getAdminMeta(session.token)
    setAdminMeta(data)
  }

  async function afterLogin(nextSession) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setSession(nextSession)
      await Promise.all([
        api.getInventoryItems(nextSession.branchCode, nextSession.token).then((data) => {
          setInventoryItems(data.items || [])
          setInventoryEdits({})
        }),
        api.getDashboardSummary(nextSession.branchCode, nextSession.token, 14).then(setDashboard),
        nextSession.role === 'admin' ? api.getAdminMeta(nextSession.token).then(setAdminMeta) : Promise.resolve(),
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function handleLogout() {
    setSession(null)
    setInventoryItems([])
    setInventoryEdits({})
    setDashboard(null)
    setAdminMeta({ branches: [], categories: [], items: [], users: [] })
    setError('')
    setNotice('')
    setActiveTab('inventory')
    setActiveAdminSection('categories')
  }

  async function handleSubmitInventory() {
    setError('')
    setNotice('')

    const missingRequired = []
    for (const item of inventoryItems) {
      if (!item.required) continue
      const edit = inventoryEdits[item.id] || {}
      const quantity = String(edit.quantity ?? item.lastQuantity ?? '').trim()
      const unit = String(edit.unit ?? item.lastUnit ?? '').trim()
      if (!quantity || !unit) missingRequired.push(item.name)
      if (quantity && (Number.isNaN(Number(quantity)) || Number(quantity) < 0)) missingRequired.push(item.name)
    }

    if (missingRequired.length) {
      setError(`Required items missing or invalid: ${[...new Set(missingRequired)].join(', ')}`)
      return
    }

    if (!changedInventoryItems.length) {
      setError('No changed items to submit.')
      return
    }

    setBusy(true)
    try {
      await api.submitInventoryUpdate(
        {
          branchCode: session.branchCode,
          submittedAt: new Date().toISOString(),
          items: changedInventoryItems.map((item) => ({ itemId: item.itemId, quantity: item.quantity, unit: item.unit })),
        },
        session.token
      )
      setNotice(`Submitted ${changedInventoryItems.length} inventory update${changedInventoryItems.length > 1 ? 's' : ''}.`)
      await Promise.all([loadInventory(), loadDashboard()])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitCategory(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.createCategory(
        {
          code: categoryForm.code,
          name: categoryForm.name,
          displayOrder: Number(categoryForm.displayOrder),
        },
        session.token
      )
      setCategoryForm({ code: '', name: '', displayOrder: 999 })
      setNotice('Category created.')
      await loadAdminMeta()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitNewItem(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.createItem(
        {
          ...newItemForm,
          minThreshold: Number(newItemForm.minThreshold),
          allowedUnits: newItemForm.allowedUnits
            .split(',')
            .map((u) => u.trim())
            .filter(Boolean),
        },
        session.token
      )
      setNewItemForm({
        sku: '',
        name: '',
        categoryCode: '',
        defaultUnit: '',
        allowedUnits: '',
        minThreshold: '',
        isRequired: false,
      })
      setNotice('Item created.')
      await Promise.all([loadAdminMeta(), loadInventory()])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitEditItem(event) {
    event.preventDefault()
    if (!editItemId) {
      setError('Select an item to edit first.')
      return
    }

    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.updateItem(
        {
          itemId: editItemId,
          minThreshold: Number(editItemForm.minThreshold),
          defaultUnit: editItemForm.defaultUnit,
          allowedUnits: editItemForm.allowedUnits
            .split(',')
            .map((u) => u.trim())
            .filter(Boolean),
        },
        session.token
      )
      setNotice('Item updated.')
      await Promise.all([loadAdminMeta(), loadInventory(), loadDashboard()])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitUser(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.createUser(userForm, session.token)
      setUserForm({ username: '', password: '', fullName: '', role: 'staff', branchCodes: [] })
      setNotice('User created.')
      await loadAdminMeta()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!session) {
    return <LoginScreen busy={busy} error={error} onLogin={afterLogin} />
  }

  const visibleModes = MODES.filter((mode) => !(mode.id === 'admin' && session.role !== 'admin'))
  const activeModeMeta = visibleModes.find((mode) => mode.id === activeTab) || visibleModes[0]

  function handleRefresh() {
    const loaders = {
      inventory: loadInventory,
      dashboard: loadDashboard,
      admin: loadAdminMeta,
    }
    const fn = loaders[activeTab]
    if (fn) fn().catch((e) => setError(e.message))
  }

  return (
    <div className={`workspace ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      {/* Mobile backdrop */}
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <h1>Inventory</h1>
          <p>{session.branchName}</p>
        </div>

        <nav className="sidebar-nav">
          {visibleModes.map((mode) => (
            <button
              key={mode.id}
              className={`nav-item ${mode.id === activeTab ? 'active' : ''}`}
              onClick={() => {
                setActiveTab(mode.id)
                setError('')
                setNotice('')
                setSidebarOpen(false)
              }}
            >
              <span>{mode.label}</span>
              <small>{mode.hint}</small>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="avatar">{session.username.charAt(0).toUpperCase()}</div>
            <div className="sidebar-user-info">
              <div className="name">{session.username}</div>
              <div className="role">{session.role}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout}>Log out</button>
        </div>
      </aside>

      <main className="main-content">
        <header className="content-topbar">
          <div className="content-title">
            <button className="menu-btn" onClick={() => setSidebarOpen((prev) => !prev)} aria-label="Toggle sidebar">
              {sidebarOpen ? '\u2715' : '\u2630'}
            </button>
            <div>
              <h2>{activeModeMeta?.label}</h2>
              <p>{activeModeMeta?.hint}</p>
            </div>
          </div>

          <div className="content-actions">
            <button className="btn-secondary refresh-btn" disabled={busy} onClick={handleRefresh} aria-label="Refresh">
              <span className="refresh-label">Refresh</span>
              <svg className="refresh-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1v4h4" /><path d="M15 15v-4h-4" />
                <path d="M13.5 6A6 6 0 0 0 3 3.5L1 5m14 6l-2 1.5A6 6 0 0 1 2.5 10" />
              </svg>
            </button>
          </div>
        </header>

        {error && <div className="banner error">{error}</div>}
        {notice && <div className="banner success">{notice}</div>}

        {activeTab === 'inventory' && (
          <section className="panel">
            {inventoryItems.length === 0 ? (
              <div className="empty-state">No inventory items found for this branch.</div>
            ) : (
              <>
                {Object.entries(groupedInventory).map(([category, items]) => (
                  <div key={category} className="category-block">
                    <h3 className="category-header">{category}</h3>
                    <div className="item-grid">
                      {items.map((item) => {
                        const edit = inventoryEdits[item.id] || {}
                        const quantity = edit.quantity ?? item.lastQuantity ?? ''
                        const unit = edit.unit ?? item.lastUnit ?? item.defaultUnit ?? ''
                        return (
                          <div key={item.id} className={`item-card ${item.required ? 'required' : ''}`}>
                            <div className="item-header">
                              <strong>{item.name}</strong>
                              {item.required && <span className="required-badge">Required</span>}
                            </div>
                            <span className="last-value">Last: {item.lastQuantity || '\u2013'} {item.lastUnit || '\u2013'}</span>
                            <div className="field-row">
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                placeholder="Qty"
                                value={quantity}
                                onChange={(e) => setInventoryEdits((prev) => ({ ...prev, [item.id]: { ...prev[item.id], quantity: e.target.value } }))}
                              />
                              <select
                                value={unit}
                                onChange={(e) => setInventoryEdits((prev) => ({ ...prev, [item.id]: { ...prev[item.id], unit: e.target.value } }))}
                              >
                                {[...(item.allowedUnits || []), item.lastUnit].filter(Boolean).filter((u, i, arr) => arr.indexOf(u) === i).map((u) => (
                                  <option key={u} value={u}>{u}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}

                <div className="submit-bar">
                  <div className="change-count">
                    <strong>{changedInventoryItems.length}</strong> item{changedInventoryItems.length !== 1 ? 's' : ''} changed
                  </div>
                  <button disabled={busy || !changedInventoryItems.length} onClick={() => setReviewOpen(true)}>
                    Review & Submit
                  </button>
                </div>

                {reviewOpen && (
                  <div className="modal-backdrop" onClick={() => !busy && setReviewOpen(false)}>
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                      <div className="modal-header">
                        <h3>Review Changes</h3>
                        <button className="modal-close" onClick={() => !busy && setReviewOpen(false)} aria-label="Close">{'\u2715'}</button>
                      </div>
                      <div className="modal-body">
                        {changedInventoryItems.length === 0 ? (
                          <div className="empty-state">No changes to review.</div>
                        ) : (
                          <table>
                            <thead>
                              <tr><th>Item</th><th>Category</th><th>Quantity</th><th>Unit</th></tr>
                            </thead>
                            <tbody>
                              {changedInventoryItems.map((item) => (
                                <tr key={item.itemId}>
                                  <td><strong>{item.name}</strong></td>
                                  <td>{item.category}</td>
                                  <td>{item.quantity}</td>
                                  <td>{item.unit}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                      <div className="modal-footer">
                        <button className="btn-secondary" onClick={() => setReviewOpen(false)} disabled={busy}>Cancel</button>
                        <button
                          disabled={busy || !changedInventoryItems.length}
                          onClick={async () => {
                            await handleSubmitInventory()
                            setReviewOpen(false)
                          }}
                        >
                          {busy ? 'Submitting\u2026' : `Submit ${changedInventoryItems.length} Change${changedInventoryItems.length !== 1 ? 's' : ''}`}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {activeTab === 'dashboard' && (
          <section className="panel">
            {!dashboard ? <div className="empty-state">Loading dashboard\u2026</div> : <DashboardView dashboard={dashboard} />}
          </section>
        )}

        {activeTab === 'admin' && session.role === 'admin' && (
          <section className="panel">
            <div className="subnav">
              {ADMIN_SECTIONS.map((section) => (
                <button
                  key={section.id}
                  className={activeAdminSection === section.id ? 'active' : ''}
                  onClick={() => setActiveAdminSection(section.id)}
                >
                  {section.label}
                </button>
              ))}
            </div>

            {activeAdminSection === 'categories' && (
              <div className="admin-section">
                <form className="form-card" onSubmit={submitCategory}>
                  <h3>Create Category</h3>
                  <div className="field">
                    <label>Code</label>
                    <input placeholder="e.g. BEV" value={categoryForm.code} onChange={(e) => setCategoryForm((p) => ({ ...p, code: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Name</label>
                    <input placeholder="e.g. Beverages" value={categoryForm.name} onChange={(e) => setCategoryForm((p) => ({ ...p, name: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Display Order</label>
                    <input type="number" value={categoryForm.displayOrder} onChange={(e) => setCategoryForm((p) => ({ ...p, displayOrder: e.target.value }))} />
                  </div>
                  <div className="form-actions">
                    <button disabled={busy}>{busy ? 'Creating\u2026' : 'Create Category'}</button>
                  </div>
                </form>
              </div>
            )}

            {activeAdminSection === 'items' && (
              <div className="admin-grid">
                <form className="form-card" onSubmit={submitNewItem}>
                  <h3>Create Item</h3>
                  <div className="field">
                    <label>SKU</label>
                    <input placeholder="e.g. RICE-BAS-5KG" value={newItemForm.sku} onChange={(e) => setNewItemForm((p) => ({ ...p, sku: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Name</label>
                    <input placeholder="e.g. Basmati Rice 5kg" value={newItemForm.name} onChange={(e) => setNewItemForm((p) => ({ ...p, name: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Category</label>
                    <select value={newItemForm.categoryCode} onChange={(e) => setNewItemForm((p) => ({ ...p, categoryCode: e.target.value }))}>
                      <option value="">Select category</option>
                      {adminMeta.categories.map((c) => <option key={c.id} value={c.code}>{c.name} ({c.code})</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label>Default Unit</label>
                    <input placeholder="e.g. kg" value={newItemForm.defaultUnit} onChange={(e) => setNewItemForm((p) => ({ ...p, defaultUnit: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Allowed Units <span className="hint">(comma separated)</span></label>
                    <input placeholder="e.g. kg, g, pcs" value={newItemForm.allowedUnits} onChange={(e) => setNewItemForm((p) => ({ ...p, allowedUnits: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Min Threshold</label>
                    <input type="number" min="0" step="0.01" placeholder="0" value={newItemForm.minThreshold} onChange={(e) => setNewItemForm((p) => ({ ...p, minThreshold: e.target.value }))} />
                  </div>
                  <label className="checkbox-row">
                    <input type="checkbox" checked={newItemForm.isRequired} onChange={(e) => setNewItemForm((p) => ({ ...p, isRequired: e.target.checked }))} />
                    Required item
                  </label>
                  <div className="form-actions">
                    <button disabled={busy}>{busy ? 'Creating\u2026' : 'Create Item'}</button>
                  </div>
                </form>

                <form className="form-card" onSubmit={submitEditItem}>
                  <h3>Edit Item</h3>
                  <div className="field">
                    <label>Select Item</label>
                    <select
                      value={editItemId}
                      onChange={(e) => {
                        const nextId = e.target.value
                        setEditItemId(nextId)
                        const selected = adminMeta.items.find((it) => it.id === nextId)
                        if (selected) {
                          setEditItemForm({
                            minThreshold: String(selected.minThreshold ?? ''),
                            defaultUnit: selected.defaultUnit || '',
                            allowedUnits: (selected.allowedUnits || []).join(', '),
                          })
                        }
                      }}
                    >
                      <option value="">Select item</option>
                      {adminMeta.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.sku})</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label>Min Threshold</label>
                    <input type="number" min="0" step="0.01" placeholder="0" value={editItemForm.minThreshold} onChange={(e) => setEditItemForm((p) => ({ ...p, minThreshold: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Default Unit</label>
                    <input placeholder="e.g. kg" value={editItemForm.defaultUnit} onChange={(e) => setEditItemForm((p) => ({ ...p, defaultUnit: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Allowed Units <span className="hint">(comma separated)</span></label>
                    <input placeholder="e.g. kg, g, pcs" value={editItemForm.allowedUnits} onChange={(e) => setEditItemForm((p) => ({ ...p, allowedUnits: e.target.value }))} />
                  </div>
                  <div className="form-actions">
                    <button disabled={busy || !editItemId}>{busy ? 'Updating\u2026' : 'Update Item'}</button>
                  </div>
                </form>
              </div>
            )}

            {activeAdminSection === 'users' && (
              <div className="admin-section">
                <form className="form-card" onSubmit={submitUser}>
                  <h3>Create User</h3>
                  <div className="field">
                    <label>Username</label>
                    <input placeholder="e.g. john.doe" value={userForm.username} onChange={(e) => setUserForm((p) => ({ ...p, username: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Full Name</label>
                    <input placeholder="e.g. John Doe" value={userForm.fullName} onChange={(e) => setUserForm((p) => ({ ...p, fullName: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Password</label>
                    <input type="password" placeholder="Min 8 characters" value={userForm.password} onChange={(e) => setUserForm((p) => ({ ...p, password: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Role</label>
                    <select value={userForm.role} onChange={(e) => setUserForm((p) => ({ ...p, role: e.target.value }))}>
                      <option value="staff">Staff</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                  <div className="field">
                    <label>Assigned Branches</label>
                    <div className="checkbox-list">
                      {adminMeta.branches.length === 0 && <span style={{ color: 'var(--muted)', fontSize: 13 }}>No branches available</span>}
                      {adminMeta.branches.map((branch) => (
                        <label key={branch.id}>
                          <input
                            type="checkbox"
                            checked={userForm.branchCodes.includes(branch.code)}
                            onChange={(e) => {
                              setUserForm((prev) => ({
                                ...prev,
                                branchCodes: e.target.checked
                                  ? [...prev.branchCodes, branch.code]
                                  : prev.branchCodes.filter((c) => c !== branch.code),
                              }))
                            }}
                          />
                          {branch.name} ({branch.code})
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="form-actions">
                    <button disabled={busy}>{busy ? 'Creating\u2026' : 'Create User'}</button>
                  </div>
                </form>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}

function LoginScreen({ onLogin, busy, error }) {
  const [form, setForm] = useState({ username: '', password: '', branchCode: '' })
  const [localError, setLocalError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setLocalError('')
    const data = await api.login({
      username: form.username.trim().toLowerCase(),
      password: form.password,
      branchCode: form.branchCode.trim().toUpperCase(),
    })
    await onLogin({
      token: data.token,
      username: data.user.username,
      role: data.user.role,
      branchCode: data.branch.code,
      branchName: data.branch.name,
    })
  }

  return (
    <div className="login-shell">
      <form
        className="login-card"
        onSubmit={(e) => submit(e).catch((err) => setLocalError(err.message || 'Login failed.'))}
      >
        <h1>Inventory Console</h1>
        <p className="subtitle">Sign in to manage branch inventory and analytics</p>
        {error && <div className="banner error">{error}</div>}
        {localError && <div className="banner error">{localError}</div>}
        <div className="field">
          <label>Username</label>
          <input placeholder="Enter your username" value={form.username} onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))} />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" placeholder="Enter your password" value={form.password} onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))} />
        </div>
        <div className="field">
          <label>Branch Code</label>
          <input placeholder="e.g. DEL01" value={form.branchCode} onChange={(e) => setForm((p) => ({ ...p, branchCode: e.target.value }))} />
        </div>
        <button disabled={busy}>{busy ? 'Signing in\u2026' : 'Sign in'}</button>
      </form>
    </div>
  )
}

function DashboardView({ dashboard }) {
  const kpis = dashboard.kpis || {}
  const daily = dashboard.dailyConsumption || []
  const maxDaily = Math.max(1, ...daily.map((x) => x.consumed || 0))

  return (
    <div className="dashboard-grid">
      <div className="kpi kpi-danger">
        <span className="kpi-label">Critically Low</span>
        <strong className="kpi-value">{kpis.criticallyLowCount ?? 0}</strong>
      </div>
      <div className="kpi kpi-warning">
        <span className="kpi-label">Order Today</span>
        <strong className="kpi-value">{kpis.orderTodayCount ?? 0}</strong>
      </div>
      <div className="kpi kpi-success">
        <span className="kpi-label">Updated Today</span>
        <strong className="kpi-value">{kpis.updatedTodayCount ?? 0}</strong>
      </div>
      <div className="kpi kpi-info">
        <span className="kpi-label">Avg Daily Consumption</span>
        <strong className="kpi-value">{kpis.avgConsumptionPerDay ?? 0}</strong>
      </div>

      <div className="card wide">
        <h3>Critically Low Items</h3>
        {(dashboard.criticallyLowItems || []).length === 0 ? (
          <div className="empty-state">No low stock alerts.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Item</th><th>Stock</th><th>Threshold</th><th>Category</th></tr>
              </thead>
              <tbody>
                {dashboard.criticallyLowItems.map((row) => (
                  <tr key={row.itemId}>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.quantity} {row.unit}</td>
                    <td>{row.minThreshold}</td>
                    <td>{row.category}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>7-Day Consumption</h3>
        {daily.length === 0 ? (
          <div className="empty-state">No consumption data yet.</div>
        ) : (
          <div className="bar-list">
            {daily.map((row) => (
              <div key={row.date} className="bar-row">
                <span>{row.date.slice(5)}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(row.consumed / maxDaily) * 100}%` }} /></div>
                <strong>{row.consumed}</strong>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Category Risk</h3>
        {(dashboard.categoryRisk || []).length === 0 ? (
          <div className="empty-state">No risk data available.</div>
        ) : (
          <div className="bar-list">
            {dashboard.categoryRisk.map((row) => (
              <div key={row.category} className="bar-row">
                <span>{row.category}</span>
                <div className="bar-track"><div className="bar-fill danger" style={{ width: `${Math.min(row.lowPct || 0, 100)}%` }} /></div>
                <strong>{row.lowPct}%</strong>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card wide">
        <h3>Top Consumption Rate</h3>
        {(dashboard.topConsumption || []).length === 0 ? (
          <div className="empty-state">Not enough history yet.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Item</th><th>Avg/Day</th><th>Total</th><th>Current Qty</th><th>Days Left</th></tr>
              </thead>
              <tbody>
                {dashboard.topConsumption.map((row) => (
                  <tr key={row.itemId}>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.avgDailyConsumption}</td>
                    <td>{row.totalConsumed}</td>
                    <td>{row.currentQuantity}</td>
                    <td>{row.daysToDeplete ?? '\u2013'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
