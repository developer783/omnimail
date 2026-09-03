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
  const [drafts, setDrafts] = useState([]);
  const [folderCounts, setFolderCounts] = useState({});

  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [activeFolder, setActiveFolder] = useState('inbox');
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');

  const [isSyncing, setIsSyncing] = useState(false);
  const [disconnectingAccount, setDisconnectingAccount] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [filters, setFilters] = useState([]);
  const [notification, setNotification] = useState(null);
  const [lastCheckedTime, setLastCheckedTime] = useState('just now');

  // Debounce search input to prevent rapid un-debounced API calls
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

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

  // Fetch emails, drafts, folder counts, connected accounts, and keyword filters
  const loadData = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const response = await api.getEmails(selectedAccountId, activeFolder, debouncedSearchQuery);
      setEmails(response.items || []);
      setAccounts(response.accounts || []);
      setFolderCounts(response.folder_counts || {});
      setFilters(response.filters || []);

      try {
        const draftsRes = await api.getDrafts(selectedAccountId);
        setDrafts(draftsRes.items || []);
      } catch (e) {
        console.error('Error fetching drafts:', e);
      }

      setLastCheckedTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

      // Keep selected email updated without depending on selectedEmail state
      setSelectedEmail(prevSelected => {
        if (!prevSelected) return null;
        const allItems = response.items || [];
        const updatedSelected = allItems.find(e => e.id === prevSelected.id) || prevSelected;
        
        const tId = updatedSelected.gmail_thread_id && updatedSelected.gmail_thread_id.trim();
        const mId = updatedSelected.gmail_message_id && updatedSelected.gmail_message_id.trim();
        const cleanSubj = updatedSelected.subject ? updatedSelected.subject.replace(/^(re|fwd|fw|reply):\s*/ig, '').replace(/\s+/g, ' ').trim().toLowerCase() : '';
        const rawThreadMsgs = allItems.filter(e => {
          if (tId && e.gmail_thread_id && e.gmail_thread_id.trim() === tId) return true;
          if (mId && (e.gmail_thread_id === mId || e.gmail_message_id === mId)) return true;
          if (cleanSubj && e.subject) {
            const eSubj = e.subject.replace(/^(re|fwd|fw|reply):\s*/ig, '').replace(/\s+/g, ' ').trim().toLowerCase();
            if (eSubj && eSubj === cleanSubj && e.account_id === updatedSelected.account_id) return true;
          }
          return e.id === updatedSelected.id;
        });

        const seenIds = new Set();
        const threadMsgs = [];
        const existingMsgs = prevSelected.threadMessages || [];
        existingMsgs.forEach(m => {
          if (m && m.id && !seenIds.has(m.id)) {
            seenIds.add(m.id);
            threadMsgs.push(m);
          }
        });
        rawThreadMsgs.forEach(m => {
          if (m && m.id) {
            if (!seenIds.has(m.id)) {
              seenIds.add(m.id);
              threadMsgs.push(m);
            } else {
              const idx = threadMsgs.findIndex(existing => existing.id === m.id);
              if (idx !== -1) threadMsgs[idx] = { ...threadMsgs[idx], ...m };
            }
          }
        });
        threadMsgs.sort((a, b) => new Date(a.received_at) - new Date(b.received_at));

        return { ...updatedSelected, threadMessages: threadMsgs.length > 0 ? threadMsgs : [updatedSelected] };
      });
    } catch (err) {
      console.error('Error loading dashboard data:', err);
    }
  }, [isAuthenticated, selectedAccountId, activeFolder, debouncedSearchQuery]);

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
    let isCancelled = false;
    if (isAuthenticated) {
      loadData();
    }
    return () => {
      isCancelled = true;
    };
  }, [loadData, isAuthenticated]);

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
    setFolderCounts(prev => ({
      ...prev,
      starred: Math.max(0, (prev.starred || 0) + (updatedStatus ? 1 : -1))
    }));
    try {
      api.updateEmailStatus(email.id, { is_starred: updatedStatus });
    } catch (err) {
      console.error('Failed to toggle star:', err);
    }
  };

  const handleToggleRead = async (email) => {
    if (email.is_read) return; // Already read
    setEmails(prev => prev.map(e => e.id === email.id ? { ...e, is_read: true } : e));
    if (selectedEmail && selectedEmail.id === email.id) {
      setSelectedEmail(prev => ({ ...prev, is_read: true }));
    }
    setFolderCounts(prev => ({
      ...prev,
      unread: Math.max(0, (prev.unread || 0) - 1)
    }));
    try {
      api.updateEmailStatus(email.id, { is_read: true });
    } catch (err) {
      console.error('Failed to toggle read:', err);
    }
  };

  const handleChangeFolderStatus = async (email, newFolder) => {
    const oldFolder = email.folder_status;
    setEmails(prev => prev.map(e => e.id === email.id ? { ...e, folder_status: newFolder } : e));
    if (selectedEmail && selectedEmail.id === email.id) {
      setSelectedEmail(prev => ({ ...prev, folder_status: newFolder }));
    }
    setFolderCounts(prev => ({
      ...prev,
      [oldFolder]: Math.max(0, (prev[oldFolder] || 0) - 1),
      [newFolder]: (prev[newFolder] || 0) + 1
    }));
    try {
      api.updateEmailStatus(email.id, { folder_status: newFolder });
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
            setSelectedDraft(null);
          }}
          activeFolder={activeFolder}
          onSelectFolder={(folderId) => {
            setActiveFolder(folderId);
            setSelectedEmail(null);
            setSelectedDraft(null);
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
          drafts={drafts}
          selectedEmailId={selectedEmail ? selectedEmail.id : null}
          selectedDraftId={selectedDraft ? selectedDraft.id : null}
          searchQuery={searchQuery}
          onSelectEmail={(email, threadMsgs) => {
            setSelectedDraft(null);
            setSelectedEmail({ ...email, threadMessages: threadMsgs || [email] });
            if (!email.is_read) {
              handleToggleRead(email);
            }
          }}
          onSelectDraft={(draft) => {
            setSelectedEmail(null);
            setSelectedDraft(draft);
          }}
          activeFolder={activeFolder}
          activeAccountEmail={activeAccountEmail}
          onToggleStar={handleToggleStar}
          onToggleRead={handleToggleRead}
        />

        <EmailDetail
          key={selectedEmail ? `email_${selectedEmail.id}` : (selectedDraft ? `draft_${selectedDraft.id}` : 'empty')}
          email={selectedEmail}
          activeDraft={selectedDraft}
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
