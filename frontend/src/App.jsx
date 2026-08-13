import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import LoginScreen from './components/LoginScreen';
import TopBar from './components/TopBar';
import Sidebar from './components/Sidebar';
import EmailList from './components/EmailList';
import EmailDetail from './components/EmailDetail';
import DisconnectModal from './components/DisconnectModal';
import ComposeModal from './components/ComposeModal';

export default function App() {
  // 1. State Declarations
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecking, setAuthChecking] = useState(true);
  const [currentUser, setCurrentUser] = useState(null);

  const [accounts, setAccounts] = useState([]);
  const [emails, setEmails] = useState([]);
  const [folderCounts, setFolderCounts] = useState({});

  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [activeFolder, setActiveFolder] = useState('inbox');
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const [isSyncing, setIsSyncing] = useState(false);
  const [disconnectingAccount, setDisconnectingAccount] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [filters, setFilters] = useState([]);
  const [notification, setNotification] = useState(null);
  const [lastCheckedTime, setLastCheckedTime] = useState('just now');

  // 2. Callback Functions (Declared BEFORE any useEffect that references them)
  const checkAuth = useCallback(async () => {
    setAuthChecking(true);
    try {
      const user = await api.getCurrentUser();
      setCurrentUser(user);
      setIsAuthenticated(true);
    } catch (e) {
      setIsAuthenticated(false);
    } finally {
      setAuthChecking(false);
    }
  }, []);

  // Fetch emails, folder counts, connected accounts, and keyword filters
  const loadData = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const response = await api.getEmails(selectedAccountId, activeFolder, searchQuery);
      setEmails(response.items || []);
      setAccounts(response.accounts || []);
      setFolderCounts(response.folder_counts || {});
      setFilters(response.filters || []);
      setLastCheckedTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

      // Keep selected email updated if it exists in current payload
      if (selectedEmail) {
        const updatedSelected = (response.items || []).find(e => e.id === selectedEmail.id);
        if (updatedSelected) {
          setSelectedEmail(updatedSelected);
        }
      }
    } catch (err) {
      console.error('Error loading dashboard data:', err);
    }
  }, [isAuthenticated, selectedAccountId, activeFolder, searchQuery, selectedEmail]);

  // 3. useEffect Hooks (All functions referenced inside are already declared above)
  useEffect(() => {
    checkAuth();

    const handleUnauthorized = () => setIsAuthenticated(false);
    window.addEventListener('auth_unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth_unauthorized', handleUnauthorized);
  }, [checkAuth]);

  // Check URL query parameters for OAuth callback redirect flags
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('account_added') === 'true') {
      const addedEmail = params.get('email');
      setNotification({
        type: 'success',
        text: addedEmail
          ? `Linked Google account ${addedEmail}! Initial emails backfilling.`
          : 'Google account linked successfully! Initial emails backfilling.'
      });
      loadData();
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (params.get('error')) {
      setNotification({ type: 'error', text: `OAuth Error: ${params.get('error')}` });
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [loadData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 4. Action Handlers
  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const result = await api.syncEmails();
      setNotification({
        type: result.status === 'error' ? 'error' : 'success',
        text: result.message
      });
      await loadData();
    } catch (err) {
      setNotification({ type: 'error', text: `Sync failed: ${err.message}` });
    } finally {
      setIsSyncing(false);
    }
  };

  const handleConfirmDisconnect = async (accountId) => {
    setIsDeleting(true);
    const targetAcc = disconnectingAccount;

    // Optimistic Update: immediately remove from UI state
    setAccounts(prev => prev.filter(a => a.id !== accountId));
    setEmails(prev => prev.filter(e => e.account_id !== accountId));
    if (selectedAccountId === accountId) {
      setSelectedAccountId(null);
    }
    if (selectedEmail && selectedEmail.account_id === accountId) {
      setSelectedEmail(null);
    }

    try {
      await api.deleteAccount(accountId);
      setNotification({
        type: 'success',
        text: `Revoked OAuth tokens and disconnected ${targetAcc?.google_email || 'account'}.`
      });
      await loadData();
    } catch (err) {
      setNotification({ type: 'error', text: `Disconnect failed: ${err.message}` });
      await loadData(); // Revert on failure
    } finally {
      setIsDeleting(false);
      setDisconnectingAccount(null);
    }
  };

  const handleToggleStar = async (email) => {
    const updatedStatus = !email.is_starred;
    setEmails(prev => prev.map(e => e.id === email.id ? { ...e, is_starred: updatedStatus } : e));
    if (selectedEmail && selectedEmail.id === email.id) {
      setSelectedEmail(prev => ({ ...prev, is_starred: updatedStatus }));
    }
    try {
      await api.updateEmailStatus(email.id, { is_starred: updatedStatus });
      await loadData();
    } catch (err) {
      console.error('Failed to toggle star:', err);
    }
  };

  const handleToggleRead = async (email) => {
    const updatedStatus = !email.is_read;
    setEmails(prev => prev.map(e => e.id === email.id ? { ...e, is_read: updatedStatus } : e));
    if (selectedEmail && selectedEmail.id === email.id) {
      setSelectedEmail(prev => ({ ...prev, is_read: updatedStatus }));
    }
    try {
      await api.updateEmailStatus(email.id, { is_read: updatedStatus });
      await loadData();
    } catch (err) {
      console.error('Failed to toggle read:', err);
    }
  };

  const handleChangeFolderStatus = async (email, newFolder) => {
    setEmails(prev => prev.map(e => e.id === email.id ? { ...e, folder_status: newFolder } : e));
    if (selectedEmail && selectedEmail.id === email.id) {
      setSelectedEmail(prev => ({ ...prev, folder_status: newFolder }));
    }
    try {
      await api.updateEmailStatus(email.id, { folder_status: newFolder });
      await loadData();
    } catch (err) {
      console.error('Failed to change folder status:', err);
    }
  };

  const handleAddFilter = async (keyword, field) => {
    try {
      await api.createFilter(keyword, field);
      setNotification({ type: 'success', text: `Added ingestion filter '${keyword}' (${field})` });
      await loadData();
    } catch (err) {
      setNotification({ type: 'error', text: err.message });
    }
  };

  const handleDeleteFilter = async (filterId) => {
    try {
      await api.deleteFilter(filterId);
      setNotification({ type: 'success', text: 'Deleted ingestion filter' });
      await loadData();
    } catch (err) {
      setNotification({ type: 'error', text: err.message });
    }
  };

  const handleLogout = async () => {
    await api.logout();
    setIsAuthenticated(false);
    setSelectedEmail(null);
    setCurrentUser(null);
  };

  // 5. Render Guards
  if (authChecking) {
    return (
      <div className="auth-wrapper">
        <div style={{ color: 'var(--text-secondary)', fontSize: '15px', fontWeight: '600' }}>
          Loading OmniMail Dashboard...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen onLoginSuccess={() => checkAuth()} />;
  }

  const activeAccountObj = accounts.find(a => a.id === selectedAccountId);
  const activeAccountEmail = activeAccountObj ? activeAccountObj.google_email : null;

  return (
    <div className="app-master">
      {/* Toast Notifications */}
      {notification && (
        <div
          style={{
            position: 'fixed',
            top: '70px',
            right: '20px',
            zIndex: 9999,
            padding: '12px 20px',
            borderRadius: '10px',
            background: notification.type === 'error' ? 'rgba(239, 68, 68, 0.95)' : 'rgba(16, 185, 129, 0.95)',
            color: 'white',
            fontWeight: '600',
            fontSize: '13px',
            boxShadow: '0 10px 25px rgba(0, 0, 0, 0.4)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}
        >
          <span>{notification.text}</span>
          <button
            onClick={() => setNotification(null)}
            style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', fontWeight: 'bold' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* TopBar Header */}
      <TopBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        lastCheckedTime={lastCheckedTime}
        onRefreshAccounts={loadData}
      />

      {/* Main 3-Pane Layout */}
      <div className="app-container">
        <Sidebar
          accounts={accounts}
          selectedAccount={selectedAccountId}
          onSelectAccount={(accId) => {
            setSelectedAccountId(accId);
            setSelectedEmail(null);
          }}
          activeFolder={activeFolder}
          onSelectFolder={(folderId) => {
            setActiveFolder(folderId);
            setSelectedEmail(null);
          }}
          folderCounts={folderCounts}
          filters={filters}
          onAddFilter={handleAddFilter}
          onDeleteFilter={handleDeleteFilter}
          onOpenCompose={() => setIsComposeOpen(true)}
          onRequestDisconnect={(acc) => setDisconnectingAccount(acc)}
          onSync={handleSync}
          isSyncing={isSyncing}
          onLogout={handleLogout}
          currentUser={currentUser}
          onRefreshAccounts={loadData}
        />

        <EmailList
          emails={emails}
          selectedEmailId={selectedEmail ? selectedEmail.id : null}
          onSelectEmail={(email) => {
            setSelectedEmail(email);
            if (!email.is_read) {
              handleToggleRead(email);
            }
          }}
          activeFolder={activeFolder}
          activeAccountEmail={activeAccountEmail}
          onToggleStar={handleToggleStar}
          onToggleRead={handleToggleRead}
        />

        <EmailDetail
          email={selectedEmail}
          onToggleStar={handleToggleStar}
          onToggleRead={handleToggleRead}
          onChangeFolderStatus={handleChangeFolderStatus}
          onRefresh={loadData}
        />
      </div>

      {/* Disconnect Account Confirmation Modal */}
      <DisconnectModal
        account={disconnectingAccount}
        isOpen={!!disconnectingAccount}
        onClose={() => setDisconnectingAccount(null)}
        onConfirm={handleConfirmDisconnect}
        isDeleting={isDeleting}
      />

      {/* Compose Message Stub Modal */}
      <ComposeModal
        isOpen={isComposeOpen}
        onClose={() => setIsComposeOpen(false)}
        accounts={accounts}
      />
    </div>
  );
}
