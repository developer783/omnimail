import React from 'react';
import {
  Inbox,
  Mail,
  Star,
  Clock,
  CheckCheck,
  Bookmark,
  Plus,
  LogOut,
  RefreshCw,
  X,
  Layers,
  AlertTriangle
} from 'lucide-react';
import { api } from '../api';

export default function Sidebar({
  accounts,
  selectedAccount,
  onSelectAccount,
  activeFolder,
  onSelectFolder,
  folderCounts,
  onOpenCompose,
  onRequestDisconnect,
  onSync,
  isSyncing,
  onLogout,
  currentUser,
  onRefreshAccounts
}) {
  const handleAddAccount = async () => {
    try {
      const url = await api.getGoogleOAuthUrl();
      window.location.href = url;
    } catch (err) {
      if (window.confirm(`${err.message}\n\nWould you like to connect a demo Google Account for instant testing?`)) {
        try {
          const demoEmail = prompt("Enter Google email address for demo account:", `recruiter.${accounts.length + 1}@gmail.com`);
          if (demoEmail) {
            await api.demoConnectAccount(demoEmail);
            if (onRefreshAccounts) onRefreshAccounts();
          }
        } catch (e) {
          alert(`Failed to add demo account: ${e.message}`);
        }
      }
    }
  };

  const navItems = [
    { id: 'inbox', label: 'Inbox', icon: Inbox, count: folderCounts?.inbox || 0 },
    { id: 'unread', label: 'Unread', icon: Mail, count: folderCounts?.unread || 0, highlight: true },
    { id: 'starred', label: 'Starred', icon: Star, count: folderCounts?.starred || 0 },
    { id: 'follow_up', label: 'Follow Up', icon: Bookmark, count: folderCounts?.follow_up || 0 },
    { id: 'replied', label: 'Replied', icon: CheckCheck, count: folderCounts?.replied || 0 },
    { id: 'snoozed', label: 'Snoozed', icon: Clock, count: folderCounts?.snoozed || 0 },
  ];

  return (
    <aside className="sidebar flex-sidebar">
      <div className="sidebar-action-container">
        <button className="btn-compose" onClick={onOpenCompose}>
          <Plus size={18} />
          <span>New Message</span>
        </button>
      </div>

      <div className="sidebar-scrollable">
        {/* Navigation Folders */}
        <div className="sidebar-group">
          <div className="sidebar-section-title">Navigation</div>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeFolder === item.id;
            return (
              <div
                key={item.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => onSelectFolder(item.id)}
              >
                <div className="nav-item-left">
                  <Icon size={18} className={isActive ? 'icon-active' : ''} />
                  <span>{item.label}</span>
                </div>
                {item.count > 0 && (
                  <span className={`badge-pill ${item.highlight ? 'badge-unread' : ''}`}>
                    {item.count}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Mailboxes Section */}
        <div className="sidebar-group">
          <div className="mailbox-header-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span className="sidebar-section-title" style={{ margin: 0 }}>
              Mailboxes ({accounts.length})
            </span>
            <button
              className="btn-text-add"
              onClick={handleAddAccount}
              title="Add Google Account"
            >
              <Plus size={14} /> Add
            </button>
          </div>

          {/* Unified view option */}
          <div
            className={`mailbox-item ${selectedAccount === null ? 'active' : ''}`}
            onClick={() => onSelectAccount(null)}
          >
            <div className="mailbox-info">
              <Layers size={16} />
              <span className="mailbox-name">All Mailboxes</span>
            </div>
            <span className="badge-pill">{accounts.reduce((acc, a) => acc + (a.email_count || 0), 0)}</span>
          </div>

          {/* Connected accounts list */}
          {accounts.length === 0 ? (
            <div style={{ padding: '12px', fontSize: '12.5px', color: '#64748b', fontStyle: 'italic', background: '#f8fafc', borderRadius: '8px', marginTop: '6px' }}>
              No accounts connected yet. Click <strong>+ Add</strong> above to connect Google Inbox.
            </div>
          ) : (
            accounts.map((acc) => {
              const isSelected = selectedAccount === acc.id;
              const firstLetter = (acc.google_email || 'G').charAt(0).toUpperCase();
              const isNeedsReauth = acc.sync_status === 'needs_reauth' || acc.sync_status === 'error';

              return (
                <div
                  key={acc.id}
                  className={`mailbox-item ${isSelected ? 'active' : ''}`}
                  onClick={() => onSelectAccount(acc.id)}
                  style={{ position: 'relative' }}
                >
                  <div className="mailbox-info">
                    <div className="account-avatar-sm" style={{ background: isNeedsReauth ? '#ef4444' : '#4f46e5' }}>
                      {firstLetter}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                      <span className="mailbox-name" title={acc.google_email}>
                        {acc.google_email}
                      </span>
                      {isNeedsReauth && (
                        <span style={{ fontSize: '10px', color: '#ef4444', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <AlertTriangle size={10} /> Re-connect
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mailbox-actions">
                    {acc.unread_count > 0 && !isNeedsReauth && (
                      <span className="badge-pill badge-unread">{acc.unread_count}</span>
                    )}

                    {isNeedsReauth ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAddAccount();
                        }}
                        style={{ padding: '2px 6px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px', color: '#dc2626', fontSize: '10.5px', fontWeight: 700, cursor: 'pointer' }}
                        title={acc.error_message || 'Click to re-authenticate account'}
                      >
                        Fix
                      </button>
                    ) : (
                      <button
                        className="btn-disconnect-hover"
                        title="Disconnect Account"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRequestDisconnect(acc);
                        }}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Sync Button */}
      <div style={{ padding: '0 16px 12px 16px' }}>
        <button
          className="btn-sync-sidebar"
          onClick={onSync}
          disabled={isSyncing}
        >
          <RefreshCw size={14} className={isSyncing ? 'spin' : ''} />
          {isSyncing ? 'Syncing...' : 'Refresh Inbox'}
        </button>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="user-profile">
          <div className="account-avatar" style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}>
            A
          </div>
          <div className="user-text">
            <span className="user-name">{currentUser?.username || 'Admin User'}</span>
            <span className="user-role">Shared Dashboard Session</span>
          </div>
        </div>

        <button
          className="btn-icon"
          title="Explicit Logout"
          onClick={onLogout}
        >
          <LogOut size={18} />
        </button>
      </div>
    </aside>
  );
}
