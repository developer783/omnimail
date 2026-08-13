import React, { useState } from 'react';
import { X, Send, Paperclip } from 'lucide-react';

export default function ComposeModal({ isOpen, onClose, accounts }) {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [selectedAccount, setSelectedAccount] = useState(accounts[0]?.id || '');

  if (!isOpen) return null;

  const handleSend = (e) => {
    e.preventDefault();
    alert(`Composition stub: Email sending via Gmail API is set up for ${to}.`);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content compose-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">New Message</div>
          <button className="btn-icon" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {accounts.length > 0 && (
            <div className="form-group">
              <label className="form-label">From Account</label>
              <select
                className="form-input"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
              >
                {accounts.map(acc => (
                  <option key={acc.id} value={acc.id}>{acc.google_email}</option>
                ))}
              </select>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">To</label>
            <input
              type="email"
              className="form-input"
              placeholder="candidate@example.com"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Subject</label>
            <input
              type="text"
              className="form-input"
              placeholder="Interview Follow-up"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Message Body</label>
            <textarea
              className="form-input"
              rows={6}
              placeholder="Write your email response..."
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              style={{ resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
            <button type="button" className="btn-icon" title="Attach file">
              <Paperclip size={18} />
            </button>
            <button type="submit" className="btn-primary" style={{ width: 'auto', padding: '10px 24px' }}>
              <Send size={16} /> Send Email
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
