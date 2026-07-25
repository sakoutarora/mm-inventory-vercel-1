import { useEffect, useState } from 'react'
import { api } from '../api'

export default function ItemPricingTab({ session }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editPrice, setEditPrice] = useState('')
  const [editUnit, setEditUnit] = useState('')
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [toast, setToast] = useState(null)

  useEffect(() => {
    loadPricing()
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  async function loadPricing() {
    setLoading(true)
    setError('')
    try {
      const data = await api.getItemPricing(session.token)
      setItems(data.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function startEdit(item) {
    setEditingId(item.id)
    setEditUnit(item.defaultUnit || '')
    // Show price in default unit (convert back from base)
    if (item.basePricePerUnit != null && item.defaultUnit) {
      const factor = getUnitFactor(item.defaultUnit)
      setEditPrice(String(Math.round(item.basePricePerUnit * factor * 100) / 100))
    } else {
      setEditPrice('')
    }
  }

  function getUnitFactor(unit) {
    const factors = { kg: 1000, gms: 1, lt: 1000, ml: 1, pcs: 1, pkt: 1 }
    return factors[unit] || 1
  }

  async function savePrice(itemId) {
    if (!editPrice || isNaN(Number(editPrice)) || Number(editPrice) < 0) {
      setError('Enter a valid non-negative price.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.updateItemBasePrice(itemId, { price: Number(editPrice), unit: editUnit }, session.token)
      setEditingId(null)
      setToast({ type: 'success', message: 'Base price updated.' })
      await loadPricing()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const filtered = search.trim()
    ? items.filter((i) =>
        [i.name, i.sku, i.category].some((v) =>
          String(v || '').toLowerCase().includes(search.trim().toLowerCase())
        )
      )
    : items

  if (loading) return <div className="empty-state">Loading pricing data...</div>

  return (
    <section className="panel">
      {error && <div className="banner error">{error}</div>}
      {toast && <div className={`app-toast ${toast.type}`}>{toast.message}</div>}

      <div className="inventory-toolbar" style={{ marginBottom: 16 }}>
        <input
          type="search"
          placeholder="Search by item, SKU, or category"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="inventory-toolbar-meta">
          {filtered.length} of {items.length} items
        </div>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          No inventory items found. Add items in the Admin section first.
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Item Name</th>
                <th>Category</th>
                <th>Default Unit</th>
                <th>Base Price (per default unit)</th>
                <th>Base Price (per base unit)</th>
                <th>Last Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id} style={item.basePricePerUnit == null ? { background: '#fff3cd' } : {}}>
                  <td><code>{item.sku}</code></td>
                  <td><strong>{item.name}</strong></td>
                  <td>{item.category}</td>
                  <td>{item.defaultUnit}</td>
                  <td>
                    {editingId === item.id ? (
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={editPrice}
                          onChange={(e) => setEditPrice(e.target.value)}
                          style={{ width: 100 }}
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') savePrice(item.id)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                        />
                        <span>/{editUnit}</span>
                      </div>
                    ) : item.basePricePerUnit != null ? (
                      `\u20B9${(item.basePricePerUnit * getUnitFactor(item.defaultUnit)).toFixed(2)}/${item.defaultUnit}`
                    ) : (
                      <span className="badge-warning">Not set</span>
                    )}
                  </td>
                  <td>
                    {item.basePricePerUnit != null
                      ? `\u20B9${item.basePricePerUnit.toFixed(4)}/${item.baseUnit}`
                      : '\u2013'}
                  </td>
                  <td>
                    {item.basePriceUpdatedAt
                      ? new Date(item.basePriceUpdatedAt).toLocaleDateString('en-IN', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })
                      : '\u2013'}
                  </td>
                  <td>
                    {editingId === item.id ? (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn-small btn-primary" disabled={saving} onClick={() => savePrice(item.id)}>
                          {saving ? 'Saving...' : 'Save'}
                        </button>
                        <button className="btn-small btn-secondary" onClick={() => setEditingId(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button className="btn-small btn-secondary" onClick={() => startEdit(item)}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
