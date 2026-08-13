import React from 'react';
import { Mail, Search, Plus } from 'lucide-react';
import { api } from '../api';

export default function TopBar({ searchQuery, onSearchChange, lastCheckedTime, onRefreshAccounts }) {
  const handleAddAccount = async () => {
    try {
      const url = await api.getGoogleOAuthUrl();
      window.location.href = url;
    } catch (err) {
      if (window.confirm(`${err.message}\n\nWould you like to connect a demo Google Account for instant testing?`)) {
        try {
          const demoEmail = prompt("Enter Google email address for demo account:", "recruiter.demo@gmail.com");
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

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="logo-badge">
          <Mail size={20} />
        </div>
        <span className="topbar-brand">OmniMail</span>
      </div>

      <div className="topbar-center">
        <div className="global-search">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            className="global-search-input"
            placeholder="Search by sender, subject, keywords..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      <div className="topbar-right">
        <div className="node-status-badge">
          <span className="live-dot-pulse"></span>
          <span className="status-label">Live Gmail Node Link</span>
          <span className="status-time">• Checked: {lastCheckedTime || 'just now'}</span>
        </div>

        <button className="btn-add-account-top" onClick={handleAddAccount}>
          <Plus size={16} />
          Google Auth
        </button>
      </div>
    </header>
  );
}
