import { useEffect } from 'react'

export default function Modal({ title, onClose, children, testid = 'modal' }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" data-testid={testid}>
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Cerrar">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Confirm({ title, message, onCancel, onConfirm, busy }) {
  return (
    <Modal title={title} onClose={onCancel} testid="confirm-dialog">
      <p className="confirm-text">{message}</p>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button className="btn btn-danger" onClick={onConfirm} disabled={busy} data-testid="confirm-delete">
          {busy ? 'Eliminando…' : 'Eliminar'}
        </button>
      </div>
    </Modal>
  )
}

export function Field({ label, name, error, children }) {
  return (
    <label className={`field ${error ? 'has-error' : ''}`}>
      <span>{label}</span>
      {children}
      {error && <small className="field-error" data-testid={`error-${name}`}>{error}</small>}
    </label>
  )
}
