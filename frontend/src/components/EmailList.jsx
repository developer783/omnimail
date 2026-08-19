import React from 'react';
import { Mail, Star, ExternalLink, Clock } from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';

export default function EmailList({
  emails,
  selectedEmailId,
  onSelectEmail,
  activeFolder,
  activeAccountEmail,
  onToggleStar,
  onToggleRead
}) {
  const groupedThreads = React.useMemo(() => {
    if (!emails || emails.length === 0) return [];
    
    const threadMap = new Map();
    
    emails.forEach(email => {
      const rawThreadId = email.gmail_thread_id && email.gmail_thread_id.trim() ? email.gmail_thread_id.trim() : null;
      const rawMsgId = email.gmail_message_id && email.gmail_message_id.trim() ? email.gmail_message_id.trim() : null;
      const threadKey = rawThreadId || rawMsgId || `single_${email.id}`;
      if (!threadMap.has(threadKey)) {
        threadMap.set(threadKey, []);
      }
      threadMap.get(threadKey).push(email);
    });
    
    const threads = [];
    threadMap.forEach((msgList, threadKey) => {
      // Sort messages chronologically (oldest first, newest last)
      msgList.sort((a, b) => new Date(a.received_at) - new Date(b.received_at));
      
      const firstMsg = msgList[0];
      const latestMsg = msgList[msgList.length - 1];
      
      const participantNames = [];
      msgList.forEach(m => {
        let name = (m.sender || 'Unknown').replace(/<.*>/, '').trim();
        if (m.sender.toLowerCase().includes('me <') || m.sender.startsWith('Me ') || (m.account_email && m.sender.toLowerCase().includes(m.account_email.toLowerCase()))) {
          name = 'Me';
        }
        if (name && !participantNames.includes(name)) {
          participantNames.push(name);
        }
      });
      
      const isUnread = msgList.some(m => !m.is_read);
      const isStarred = msgList.some(m => m.is_starred);
      const hasReplied = msgList.some(m => m.folder_status === 'replied' || m.sender.startsWith('Me '));

      threads.push({
        threadId: threadKey,
        messages: msgList,
        latestMessage: latestMsg,
        firstMessage: firstMsg,
        subject: firstMsg.subject || latestMsg.subject || '(No Subject)',
        participantNames,
        sendersDisplay: participantNames.join(', '),
        messageCount: msgList.length,
        isUnread,
        isStarred,
        hasReplied,
        receivedAt: latestMsg.received_at,
        accountEmail: latestMsg.account_email
      });
    });
    
    // Sort threads by latest message timestamp descending
    threads.sort((a, b) => new Date(b.receivedAt) - new Date(a.receivedAt));
    return threads;
  }, [emails]);

  const formatDateInfo = (dateString) => {
    try {
      let dateStr = dateString;
      if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
        dateStr = dateStr + 'Z';
      }
      const d = new Date(dateStr);
      const now = new Date();
      const diffHours = (now.getTime() - d.getTime()) / (1000 * 60 * 60);

      const relativeTimeStr = formatDistanceToNow(d, { addSuffix: true });
      const isExpiringSoon = diffHours >= 20 && diffHours < 24;

      return {
        formattedStr: relativeTimeStr,
        diffHours,
        isExpiringSoon,
        hoursLeft: Math.max(0, Math.round(24 - diffHours))
      };
    } catch (e) {
      return { formattedStr: dateString, diffHours: 0, isExpiringSoon: false, hoursLeft: 24 };
    }
  };

  const getFolderTitle = () => {
    switch (activeFolder) {
      case 'unread': return 'Unread Threads (Last 24h)';
      case 'starred': return 'Starred Threads';
      case 'follow_up': return 'Follow Up Needed';
      case 'replied': return 'Replied Threads';
      case 'snoozed': return 'Snoozed Messages';
      default: return 'Inbox Threads (Last 24h)';
    }
  };

  const openGmailDeepLink = (email, e) => {
    e.stopPropagation();
    const targetUrl = `https://mail.google.com/mail/?authuser=${encodeURIComponent(email.account_email)}#inbox/${email.gmail_message_id}`;
    window.open(targetUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="inbox-pane">
      <div className="inbox-header">
        <div className="inbox-title-row">
          <div className="inbox-title">{getFolderTitle()}</div>
          <span className="inbox-count-badge">
            {groupedThreads.length} thread{groupedThreads.length === 1 ? '' : 's'}
          </span>
        </div>

        {activeAccountEmail && (
          <div className="active-account-filter-tag">
            Filter: <strong>{activeAccountEmail}</strong>
          </div>
        )}
      </div>

      <div className="email-list">
        {groupedThreads.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Mail size={28} />
            </div>
            <div>
              <div style={{ fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>
                No active messages in {activeFolder}
              </div>
              <div style={{ fontSize: '13px', color: '#64748b' }}>
                Only inbound emails received in the trailing 24 hours are retained.
              </div>
            </div>
          </div>
        ) : (
          groupedThreads.map((thread) => {
            const isSelected = thread.messages.some(m => m.id === selectedEmailId);
            const isUnread = thread.isUnread;
            const dateInfo = formatDateInfo(thread.receivedAt);
            const targetMsgForSelection = thread.latestMessage;

            return (
              <div
                key={thread.threadId}
                className={`email-card ${isSelected ? 'selected' : ''} ${isUnread ? 'unread-card' : ''}`}
                onClick={() => onSelectEmail(targetMsgForSelection, thread.messages)}
              >
                <div className="email-card-top">
                  <div className="sender-row">
                    {isUnread && <span className="unread-dot" title="Unread" />}
                    <span className={`email-sender ${isUnread ? 'bold-text' : ''}`} title={thread.sendersDisplay}>
                      {thread.sendersDisplay}
                    </span>
                    {thread.messageCount > 1 && (
                      <span style={{
                        fontSize: '11px',
                        fontWeight: 700,
                        color: '#4f46e5',
                        background: '#e0e7ff',
                        padding: '1px 6px',
                        borderRadius: '99px',
                        marginLeft: '4px'
                      }}>
                        {thread.messageCount}
                      </span>
                    )}
                  </div>
                  <span className="email-time">{dateInfo.formattedStr}</span>
                </div>

                <div className={`email-subject ${isUnread ? 'bold-text' : ''}`} title={thread.subject}>
                  {thread.subject}
                </div>

                <div className="email-card-bottom">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="account-tag" title={`Belongs to ${thread.accountEmail}`}>
                      {thread.accountEmail}
                    </span>

                    {/* Expiring Soon Badge (over 20h old) */}
                    {dateInfo.isExpiringSoon && !thread.hasReplied && (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          fontSize: '10.5px',
                          fontWeight: 700,
                          color: '#dc2626',
                          background: '#fef2f2',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          border: '1px solid #fecaca'
                        }}
                        title={`Received ${Math.round(dateInfo.diffHours)}h ago. Will roll off in ~${dateInfo.hoursLeft}h`}
                      >
                        <Clock size={11} /> Expiring ({dateInfo.hoursLeft}h left)
                      </span>
                    )}
                  </div>

                  <div className="card-quick-actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }} onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn-star"
                      title="View in Gmail"
                      onClick={(e) => openGmailDeepLink(thread.latestMessage, e)}
                    >
                      <ExternalLink size={14} color="var(--text-muted)" />
                    </button>

                    <button
                      className={`btn-star ${thread.isStarred ? 'starred' : ''}`}
                      title={thread.isStarred ? 'Unstar' : 'Star'}
                      onClick={() => onToggleStar(thread.latestMessage)}
                    >
                      <Star size={14} fill={thread.isStarred ? '#f59e0b' : 'none'} color={thread.isStarred ? '#f59e0b' : 'var(--text-muted)'} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
