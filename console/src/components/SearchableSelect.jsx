import { useState, useRef, useEffect } from 'react'

export default function SearchableSelect({
  options = [],
  value = '',
  onChange,
  placeholder = 'Search...',
  allowFreeText = false,
  onCreateNew = null,
  style = {},
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const wrapperRef = useRef(null)
  const inputRef = useRef(null)

  // Derive display text from value
  const selected = options.find((o) => o.value === value)
  const displayText = selected ? selected.label : (allowFreeText ? value : '')

  // Sync query when value changes externally
  useEffect(() => {
    if (!open) setQuery(displayText)
  }, [value, displayText, open])

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
        if (!allowFreeText && !selected) setQuery(displayText)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [allowFreeText, selected, displayText])

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes((query || '').toLowerCase())
  )

  function handleInputChange(e) {
    const val = e.target.value
    setQuery(val)
    setOpen(true)
    setHighlightIdx(0)
    if (allowFreeText) onChange(val)
  }

  function handleSelect(opt) {
    onChange(opt.value)
    setQuery(opt.label)
    setOpen(false)
    setHighlightIdx(-1)
  }

  function handleClear(e) {
    e.stopPropagation()
    onChange('')
    setQuery('')
    setOpen(false)
    inputRef.current?.focus()
  }

  function handleKeyDown(e) {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      setOpen(true)
      return
    }
    if (!open) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightIdx >= 0 && highlightIdx < filtered.length) {
        handleSelect(filtered[highlightIdx])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="searchable-select" ref={wrapperRef} style={style}>
      <div className="searchable-select-input-wrap">
        <input
          ref={inputRef}
          type="text"
          className="searchable-select-input"
          value={open ? query : displayText}
          placeholder={placeholder}
          onChange={handleInputChange}
          onFocus={() => { setOpen(true); setQuery(displayText) }}
          onKeyDown={handleKeyDown}
        />
        {(value || query) && (
          <button
            type="button"
            className="searchable-select-clear"
            onClick={handleClear}
            tabIndex={-1}
          >
            &#10005;
          </button>
        )}
      </div>
      {open && filtered.length > 0 && (
        <ul className="searchable-select-dropdown">
          {filtered.slice(0, 50).map((opt, i) => (
            <li
              key={opt.value}
              className={`searchable-select-option ${i === highlightIdx ? 'highlighted' : ''} ${opt.value === value ? 'selected' : ''}`}
              onMouseDown={() => handleSelect(opt)}
              onMouseEnter={() => setHighlightIdx(i)}
            >
              {opt.label}
            </li>
          ))}
          {filtered.length > 50 && (
            <li className="searchable-select-option" style={{ color: '#94a3b8', fontStyle: 'italic' }}>
              +{filtered.length - 50} more - type to narrow
            </li>
          )}
          {onCreateNew && query && (
            <li
              className="searchable-select-option searchable-select-create"
              onMouseDown={(e) => { e.preventDefault(); onCreateNew(query) }}
            >
              + Create new item
            </li>
          )}
        </ul>
      )}
      {open && filtered.length === 0 && query && (
        <ul className="searchable-select-dropdown">
          <li className="searchable-select-option" style={{ color: '#94a3b8', fontStyle: 'italic' }}>
            {allowFreeText ? `Use "${query}" as new entry` : 'No matches found'}
          </li>
          {onCreateNew && (
            <li
              className="searchable-select-option searchable-select-create"
              onMouseDown={(e) => { e.preventDefault(); onCreateNew(query) }}
            >
              + Create new item
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
