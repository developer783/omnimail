import React, { useState } from 'react';
import { X, Trash2, Plus, AlertTriangle, CheckCircle, RefreshCw } from 'lucide-react';
import { api } from '../api';

export default function AccountModal({ accounts, isOpen, onClose, onRefreshAccounts }) {
  const [deletingId, setDeletingId] = useState(null);

  if (!isOpen) return null;

  const handleDelete = async (accountId, email) => {
    if (!window.confirm(`Are you sure you want to disconnect ${email}? All synced emails for this account will be removed.`)) {
      return;
    }
    setDeletingId(accountId);
    try {
      await api.deleteAccount(accountId);
      onRefreshAccounts();
    } catch (err) {
      alert(`Failed to delete account: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleAddAccount = async () => {
    try {
      const url = await api.getGoogleOAuthUrl();
      window.location.href = url;
    } catch (err) {
      alert(`Failed to start Google OAuth: ${err.message}`);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Connected Google Accounts</div>
          <button className="btn-icon" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '360px', overflowY: 'auto' }}>
          {accounts.length === 0 ? (
            <div style={{ padding: '20px', textAlignment: 'center', color: 'var(--text-muted)' }}>
              No Google accounts currently linked.
            </div>
          ) : (
            accounts.map((acc) => (
              <div
                key={acc.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyConstraints: 'space-between',
                  padding: '14px 16px',
                  borderRadius: '12px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: '600', fontSize: '14px' }}>{acc.google_email}</span>
                    {acc.sync_status === 'error' ? (
                      <span style={{ fontSize: '11px', color: 'var(--accent-danger)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <AlertTriangle size={12} /> Sync Error
                      </span>
                    ) : (
                      <span style={{ fontSize: '11px', color: 'var(--accent-success)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <CheckCircle size={12} /> Active
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Synced {acc.email_count} email(s) • Connected on {new Date(acc.connected_at).toLocaleDateString()}
                  </div>
                  {acc.error_message && (
                    <div style={{ fontSize: '11px', color: '#fca5a5', marginTop: '2px' }}>
                      {acc.error_message}
                    </div>
                  )}
                </div>

                <button
                  className="btn-icon"
                  style={{ color: 'var(--accent-danger)' }}
                  onClick={() => handleDelete(acc.id, acc.google_email)}
                  disabled={deletingId === acc.id}
                  title="Disconnect Account"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            ))
          )}
        </div>

        <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
          <button className="btn-primary" onClick={handleAddAccount}>
            <Plus size={18} /> Add Another Account
          </button>
        </div>
      </div>
    </div>
  );
}
