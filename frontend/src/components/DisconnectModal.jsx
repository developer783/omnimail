import React from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';

export default function DisconnectModal({ account, isOpen, onClose, onConfirm, isDeleting }) {
  if (!isOpen || !account) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content disconnect-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-danger)' }}>
            <AlertTriangle size={20} />
            Confirm Account Disconnect
          </div>
          <button className="btn-icon" onClick={onClose} disabled={isDeleting}>
            <X size={18} />
          </button>
        </div>

        <div style={{ fontSize: '14px', lineHeight: '1.6', color: 'var(--text-secondary)' }}>
          This will revoke Google OAuth credentials and remove <strong style={{ color: 'var(--text-primary)' }}>{account.google_email}</strong> and <strong>all its synced emails</strong> from the dashboard for everyone.
          <br /><br />
          <span style={{ fontSize: '13px', color: '#fca5a5' }}>
            ⚠️ This operation is permanent. Re-connecting the account later starts fresh.
          </span>
        </div>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
          <button className="btn-secondary" onClick={onClose} disabled={isDeleting}>
            Cancel
          </button>
          <button
            className="btn-danger"
            onClick={() => onConfirm(account.id)}
            disabled={isDeleting}
          >
            {isDeleting ? (
              'Revoking & Deleting...'
            ) : (
              <>
                <Trash2 size={16} /> Disconnect Account
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
