import { useEffect, useState } from 'react'
import { api } from '../api'

export default function UpdateHistoryTab({ session }) {
  const [updates, setUpdates] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Detail view
  const [selectedUpdate, setSelectedUpdate] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => { loadHistory() }, [offset])

  async function loadHistory() {
    setLoading(true)
    setError('')
    try {
      const data = await api.getUpdateHistory(session.branchCode, session.token, limit, offset)
      setUpdates(data.updates || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function viewDetail(updateId) {
    setDetailLoading(true)
    setError('')
    try {
      const data = await api.getUpdateDetail(updateId, session.token)
      setSelectedUpdate(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setDetailLoading(false)
    }
  }

  function formatDelta(delta) {
    if (delta === null || delta === undefined) return '\u2013'
    const sign = delta > 0 ? '+' : ''
    return `${sign}${delta}`
  }

  function deltaClass(delta) {
    if (delta === null || delta === undefined || delta === 0) return ''
    return delta > 0 ? 'delta-positive' : 'delta-negative'
  }

  // Detail view of a single update
  if (selectedUpdate) {
    const u = selectedUpdate.update
    const prev = selectedUpdate.previousUpdate

    return (
      <section className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3>Update Detail</h3>
          <button className="btn-secondary" onClick={() => setSelectedUpdate(null)}>
            Back to History
          </button>
        </div>

        <div className="dashboard-grid" style={{ marginBottom: 20 }}>
          <div className="kpi kpi-info">
            <span className="kpi-label">Submitted</span>
            <strong className="kpi-value" style={{ fontSize: 14 }}>{u.submittedAtIST}</strong>
          </div>
          <div className="kpi kpi-success">
            <span className="kpi-label">Updated By</span>
            <strong className="kpi-value" style={{ fontSize: 16 }}>{u.updatedBy}</strong>
          </div>
          <div className="kpi kpi-warning">
            <span className="kpi-label">Items Changed</span>
            <strong className="kpi-value">{u.itemCount}</strong>
          </div>
        </div>

        {prev && (
          <div style={{ marginBottom: 16, padding: '10px 14px', background: '#f8fafc', borderRadius: 8, fontSize: 13, color: '#64748b' }}>
            Previous update: {prev.submittedAtIST} by {prev.updatedBy} ({prev.itemCount} items changed)
          </div>
        )}

        <h4>Changed Items</h4>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Previous</th>
                <th></th>
                <th>New</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {(u.items || []).map((item) => {
                const prevQty = item.previousQuantityBase != null ? item.previousQuantityBase : item.previousQuantity
                const newQty = item.newQuantityBase != null ? item.newQuantityBase : item.newQuantity
                const delta = item.deltaQuantityBase != null ? item.deltaQuantityBase : item.deltaQuantity
                const unit = item.baseUnit || item.newUnit || ''

                return (
                  <tr key={item.itemId} className={item.crossedBelowThreshold ? 'row-danger' : ''}>
                    <td>
                      <strong>{item.name}</strong>
                      <br /><span style={{ fontSize: 11, color: '#94a3b8' }}>{item.sku}</span>
                      {item.crossedBelowThreshold && (
                        <span style={{ display: 'inline-block', marginLeft: 6, padding: '1px 6px', background: '#fef2f2', color: '#dc2626', borderRadius: 4, fontSize: 11 }}>
                          Below threshold
                        </span>
                      )}
                    </td>
                    <td>{item.category}</td>
                    <td>{prevQty != null ? `${prevQty} ${item.previousUnit || unit}` : '\u2013 (new)'}</td>
                    <td style={{ color: '#94a3b8' }}>{'\u2192'}</td>
                    <td><strong>{newQty} {unit}</strong></td>
                    <td className={deltaClass(delta)}>
                      <strong>{formatDelta(delta)}</strong> {unit}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {u.snapshot && u.snapshot.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <h4>Full Snapshot at this Update ({u.snapshot.length} items)</h4>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Item</th><th>Category</th><th>Quantity</th><th>Unit</th></tr>
                </thead>
                <tbody>
                  {u.snapshot.map((s) => (
                    <tr key={s.itemId}>
                      <td><strong>{s.name}</strong><br /><span style={{ fontSize: 11, color: '#94a3b8' }}>{s.sku}</span></td>
                      <td>{s.category}</td>
                      <td>{s.quantityBase != null ? s.quantityBase : s.quantity}</td>
                      <td>{s.baseUnit || s.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    )
  }

  // Loading detail
  if (detailLoading) {
    return (
      <section className="panel">
        <div className="skeleton-list">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton-row">
              <div className="skeleton-cell" style={{ width: '100%', height: 48 }} />
            </div>
          ))}
        </div>
      </section>
    )
  }

  // Main list view
  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <section className="panel">
      {error && <div className="banner error">{error}</div>}

      <div style={{ marginBottom: 16 }}>
        <strong>{total}</strong> update{total !== 1 ? 's' : ''} found
      </div>

      {loading ? (
        <div className="skeleton-list">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="skeleton-row">
              <div className="skeleton-cell" style={{ width: '100%', height: 64 }} />
            </div>
          ))}
        </div>
      ) : updates.length === 0 ? (
        <div className="empty-state">No inventory updates found for this branch.</div>
      ) : (
        <>
          <div className="update-history-list">
            {updates.map((u) => (
              <div
                key={u.id}
                className="update-history-card"
                onClick={() => viewDetail(u.id)}
                style={{ cursor: 'pointer' }}
              >
                <div className="update-history-header">
                  <div>
                    <strong>{u.submittedAtIST}</strong>
                    <span style={{ marginLeft: 12, color: '#64748b', fontSize: 13 }}>by {u.updatedBy}</span>
                  </div>
                  <span className="update-history-badge">{u.itemCount} item{u.itemCount !== 1 ? 's' : ''} changed</span>
                </div>
                {u.items && u.items.length > 0 && (
                  <div className="update-history-items">
                    {u.items.slice(0, 5).map((item) => {
                      const delta = item.deltaQuantityBase != null ? item.deltaQuantityBase : item.deltaQuantity
                      const unit = item.baseUnit || item.newUnit || ''
                      return (
                        <span key={item.itemId} className="update-history-item-tag">
                          {item.name}
                          <span className={deltaClass(delta)} style={{ marginLeft: 4 }}>
                            {formatDelta(delta)} {unit}
                          </span>
                        </span>
                      )
                    })}
                    {u.items.length > 5 && (
                      <span className="update-history-item-tag" style={{ color: '#94a3b8' }}>
                        +{u.items.length - 5} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 20, alignItems: 'center' }}>
              <button
                className="btn-secondary"
                disabled={currentPage <= 1}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                style={{ padding: '6px 14px' }}
              >
                Previous
              </button>
              <span style={{ color: '#64748b', fontSize: 14 }}>
                Page {currentPage} of {totalPages}
              </span>
              <button
                className="btn-secondary"
                disabled={currentPage >= totalPages}
                onClick={() => setOffset(offset + limit)}
                style={{ padding: '6px 14px' }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
