import { useEffect, useState } from 'react'
import { api } from '../api'
import BillsTab from './BillsTab'

export default function FoodCostTab({ session }) {
  const [snapshots, setSnapshots] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [openingDate, setOpeningDate] = useState('')
  const [openingId, setOpeningId] = useState('')
  const [closingDate, setClosingDate] = useState('')
  const [closingId, setClosingId] = useState('')
  const [calculating, setCalculating] = useState(false)
  const [result, setResult] = useState(null)

  // Inline bill entry
  const [showAddBill, setShowAddBill] = useState(false)

  // Base price check
  const [itemsWithoutPrice, setItemsWithoutPrice] = useState([])
  const [priceCheckDone, setPriceCheckDone] = useState(false)

  useEffect(() => { loadSnapshots(); checkBasePrices() }, [])

  // Browser back button support
  useEffect(() => {
    function onPopState() {
      if (showAddBill) {
        setShowAddBill(false)
      } else if (result) {
        setResult(null)
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [showAddBill, result])

  async function loadSnapshots() {
    setLoading(true)
    setError('')
    try {
      const data = await api.getSnapshots(session.branchCode, session.token)
      setSnapshots(data.snapshots || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function checkBasePrices() {
    try {
      const data = await api.getItemPricing(session.token)
      const missing = (data.items || []).filter((i) => i.basePricePerUnit == null)
      setItemsWithoutPrice(missing)
      setPriceCheckDone(true)
    } catch (_) {
      setPriceCheckDone(true)
    }
  }

  async function calculate() {
    if (!openingId || !closingId) return
    setCalculating(true)
    setError('')
    setResult(null)
    try {
      const data = await api.getFoodCost({
        branchCode: session.branchCode,
        openingUpdateId: openingId,
        closingUpdateId: closingId,
      }, session.token)
      history.pushState({ foodcostView: 'result' }, '')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setCalculating(false)
    }
  }

  function groupByDate(snaps) {
    const groups = {}
    for (const s of snaps) {
      // createdAtIST from API is "25 Jul 2026, 07:10 PM IST" -- extract date part
      const date = s.createdAtIST
        ? s.createdAtIST.split(',')[0].trim()
        : 'Unknown'
      if (!groups[date]) groups[date] = []
      groups[date].push(s)
    }
    return groups
  }

  function formatTime(snap) {
    if (!snap.createdAtIST) return ''
    // createdAtIST from API is "25 Jul 2026, 07:10 PM IST" -- extract time part
    const parts = snap.createdAtIST.split(',')
    return parts.length > 1 ? parts[1].replace('IST', '').trim() : ''
  }

  function formatDate(iso) {
    if (!iso) return '\u2013'
    return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })
  }

  // Inline bill add callback
  function onBillAdded() {
    setShowAddBill(false)
    // Re-run calculation if we already had a result
    if (openingId && closingId) calculate()
  }

  if (loading) {
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

  // Inline bill creation
  if (showAddBill) {
    return (
      <section className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3>Add Bill (from Food Cost)</h3>
          <button className="btn-secondary" onClick={() => history.back()}>Back to Results</button>
        </div>
        <BillsTab session={session} />
      </section>
    )
  }

  // Show result view
  if (result) {
    const { summary, items, billsUsed, warnings } = result
    return (
      <section className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3>Food Cost Report</h3>
          <button className="btn-secondary" onClick={() => history.back()}>Back to Picker</button>
        </div>

        {/* Period info */}
        <div style={{ marginBottom: 16, color: '#64748b', fontSize: 13 }}>
          Period: {formatDate(summary.period?.from)} — {formatDate(summary.period?.to)}
        </div>

        {/* KPI Cards */}
        <div className="dashboard-grid" style={{ marginBottom: 24 }}>
          <div className="kpi kpi-info">
            <span className="kpi-label">Opening Value</span>
            <strong className="kpi-value">{'\u20B9'}{summary.openingValue?.toLocaleString('en-IN')}</strong>
          </div>
          <div className="kpi kpi-success">
            <span className="kpi-label">+ Purchases</span>
            <strong className="kpi-value">{'\u20B9'}{summary.purchaseValue?.toLocaleString('en-IN')}</strong>
            <small>{summary.billCount} bill(s)</small>
          </div>
          <div className="kpi kpi-warning">
            <span className="kpi-label">Closing Value</span>
            <strong className="kpi-value">{'\u20B9'}{summary.closingValue?.toLocaleString('en-IN')}</strong>
          </div>
          <div className="kpi kpi-danger">
            <span className="kpi-label">= Food Cost</span>
            <strong className="kpi-value">{'\u20B9'}{summary.foodCostValue?.toLocaleString('en-IN')}</strong>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginBottom: 20, color: '#64748b', fontSize: 14, fontStyle: 'italic' }}>
          Opening + Purchases &minus; Closing = Food Cost
        </div>

        {warnings.length > 0 && (
          <div className="banner warning" style={{ marginBottom: 16 }}>
            <strong>{warnings.length} item(s) excluded</strong> (no price data):
            {' '}{warnings.map((w) => w.itemName).join(', ')}.
            <span style={{ marginLeft: 8 }}>
              Set base prices in the <strong>Item Pricing</strong> tab to include them.
            </span>
          </div>
        )}

        {/* Item Breakdown */}
        <h4>Item Breakdown</h4>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Category</th><th>Opening Qty</th><th>Purchased Qty</th>
                <th>Closing Qty</th><th>Price/unit</th>
                <th>Opening ({'\u20B9'})</th><th>Purchase ({'\u20B9'})</th>
                <th>Closing ({'\u20B9'})</th><th>Cost ({'\u20B9'})</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.itemId}>
                  <td><strong>{item.name}</strong></td>
                  <td>{item.category}</td>
                  <td>{item.openingQtyBase} {item.openingUnit}</td>
                  <td>{item.purchasedQtyBase > 0 ? `${item.purchasedQtyBase} ${item.openingUnit}` : '\u2013'}</td>
                  <td>{item.closingQtyBase} {item.closingUnit}</td>
                  <td>
                    {'\u20B9'}{item.effectivePricePerBaseUnit}/{item.openingUnit}
                    {item.priceSource === 'base_price' && (
                      <span
                        title="Using base price \u2014 no purchase bills found in this period"
                        style={{ cursor: 'help', color: '#d97706' }}
                      > *</span>
                    )}
                  </td>
                  <td>{item.openingValue.toLocaleString('en-IN')}</td>
                  <td>{item.purchaseValue > 0 ? item.purchaseValue.toLocaleString('en-IN') : '\u2013'}</td>
                  <td>{item.closingValue.toLocaleString('en-IN')}</td>
                  <td><strong>{item.costContribution.toLocaleString('en-IN')}</strong></td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                <td colSpan={6}>Total</td>
                <td>{summary.openingValue?.toLocaleString('en-IN')}</td>
                <td>{summary.purchaseValue?.toLocaleString('en-IN')}</td>
                <td>{summary.closingValue?.toLocaleString('en-IN')}</td>
                <td>{summary.foodCostValue?.toLocaleString('en-IN')}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Legend */}
        <div style={{ marginTop: 8, fontSize: 12, color: '#94a3b8' }}>
          * Using manually set base price — no purchase bills found for this item in the selected period
        </div>

        {/* Bills Used */}
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h4 style={{ margin: 0 }}>Bills Included ({billsUsed.length})</h4>
            <button className="btn-secondary" onClick={() => { history.pushState({ foodcostView: 'addBill' }, ''); setShowAddBill(true) }}>+ Add Bill</button>
          </div>

          {billsUsed.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              No bills found in this period. Add a bill to improve food cost accuracy.
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Date</th><th>Order #</th><th>Supplier</th><th>Source</th><th>Items</th><th>Total ({'\u20B9'})</th></tr>
                </thead>
                <tbody>
                  {billsUsed.map((b) => (
                    <tr key={b.billId}>
                      <td>{formatDate(b.billDate)}</td>
                      <td>{b.orderNo || '\u2013'}</td>
                      <td>{b.supplierName}</td>
                      <td><span className={`badge-${b.source === 'hyperpure' ? 'info' : 'default'}`}>{b.source === 'hyperpure' ? 'HP' : 'Manual'}</span></td>
                      <td>{b.itemCount}</td>
                      <td>{'\u20B9'}{b.grandTotal?.toLocaleString('en-IN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    )
  }

  // Snapshot Picker
  const grouped = groupByDate(snapshots)

  return (
    <section className="panel">
      {error && <div className="banner error">{error}</div>}

      {/* Base price warning */}
      {priceCheckDone && itemsWithoutPrice.length > 0 && (
        <div className="banner warning" style={{ marginBottom: 16 }}>
          <strong>{itemsWithoutPrice.length} item(s)</strong> have no base price set.
          Items without prices or purchase bills will be excluded from food cost calculation.
          <span style={{ marginLeft: 8 }}>
            Set prices in the <strong>Item Pricing</strong> tab.
          </span>
        </div>
      )}

      {snapshots.length === 0 ? (
        <div className="empty-state">
          <p style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>No inventory snapshots found</p>
          <p>Stock must be updated from the mobile app first to create snapshots for food cost calculation.</p>
        </div>
      ) : (
        <>
          <div className="snapshot-picker" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            {/* Opening Picker */}
            <div>
              <h4>Opening Stock</h4>
              <p style={{ color: '#64748b', fontSize: 13, marginBottom: 8 }}>Select the inventory snapshot at the start of the period</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <select
                  className="select-dropdown"
                  value={openingDate}
                  onChange={(e) => { setOpeningDate(e.target.value); setOpeningId('') }}
                >
                  <option value="">-- Pick a date --</option>
                  {Object.keys(grouped).map((date) => (
                    <option key={date} value={date}>{date}</option>
                  ))}
                </select>
                {openingDate && grouped[openingDate] && (
                  <select
                    className="select-dropdown"
                    value={openingId}
                    onChange={(e) => setOpeningId(e.target.value)}
                  >
                    <option value="">-- Pick a snapshot --</option>
                    {grouped[openingDate].map((s) => (
                      <option key={s.id} value={s.id}>
                        {formatTime(s)} - by {s.updatedBy} ({s.itemCount} items)
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* Closing Picker */}
            <div>
              <h4>Closing Stock</h4>
              <p style={{ color: '#64748b', fontSize: 13, marginBottom: 8 }}>Select the inventory snapshot at the end of the period</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <select
                  className="select-dropdown"
                  value={closingDate}
                  onChange={(e) => { setClosingDate(e.target.value); setClosingId('') }}
                >
                  <option value="">-- Pick a date --</option>
                  {Object.keys(grouped).map((date) => (
                    <option key={date} value={date}>{date}</option>
                  ))}
                </select>
                {closingDate && grouped[closingDate] && (
                  <select
                    className="select-dropdown"
                    value={closingId}
                    onChange={(e) => setClosingId(e.target.value)}
                  >
                    <option value="">-- Pick a snapshot --</option>
                    {grouped[closingDate].map((s) => (
                      <option key={s.id} value={s.id}>
                        {formatTime(s)} - by {s.updatedBy} ({s.itemCount} items)
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 20, textAlign: 'center' }}>
            <button
              className="btn-primary"
              disabled={!openingId || !closingId || calculating}
              onClick={calculate}
              style={{ padding: '12px 32px', fontSize: 16 }}
            >
              {calculating ? (
                <>
                  <span className="spinner-inline" /> Calculating...
                </>
              ) : 'Calculate Food Cost'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
