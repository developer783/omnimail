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
  const formatDateInfo = (dateString) => {
    try {
      const d = new Date(dateString);
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
      case 'unread': return 'Unread Messages (Last 24h)';
      case 'starred': return 'Starred Threads';
      case 'follow_up': return 'Follow Up Needed';
      case 'replied': return 'Replied Emails';
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
            {emails.length} thread{emails.length === 1 ? '' : 's'}
          </span>
        </div>

        {activeAccountEmail && (
          <div className="active-account-filter-tag">
            Filter: <strong>{activeAccountEmail}</strong>
          </div>
        )}
      </div>

      <div className="email-list">
        {emails.length === 0 ? (
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
          emails.map((email) => {
            const isSelected = selectedEmailId === email.id;
            const isUnread = !email.is_read;
            const dateInfo = formatDateInfo(email.received_at);

            return (
              <div
                key={email.id}
                className={`email-card ${isSelected ? 'selected' : ''} ${isUnread ? 'unread-card' : ''}`}
                onClick={() => onSelectEmail(email)}
              >
                <div className="email-card-top">
                  <div className="sender-row">
                    {isUnread && <span className="unread-dot" title="Unread" />}
                    <span className={`email-sender ${isUnread ? 'bold-text' : ''}`} title={email.sender}>
                      {email.sender}
                    </span>
                  </div>
                  <span className="email-time">{dateInfo.formattedStr}</span>
                </div>

                <div className={`email-subject ${isUnread ? 'bold-text' : ''}`} title={email.subject}>
                  {email.subject || '(No Subject)'}
                </div>

                <div className="email-card-bottom">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="account-tag" title={`Belongs to ${email.account_email}`}>
                      {email.account_email}
                    </span>

                    {/* Expiring Soon Badge (over 20h old) */}
                    {dateInfo.isExpiringSoon && email.folder_status !== 'replied' && (
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
                      onClick={(e) => openGmailDeepLink(email, e)}
                    >
                      <ExternalLink size={14} color="var(--text-muted)" />
                    </button>

                    <button
                      className={`btn-star ${email.is_starred ? 'starred' : ''}`}
                      title={email.is_starred ? 'Unstar' : 'Star'}
                      onClick={() => onToggleStar(email)}
                    >
                      <Star size={14} fill={email.is_starred ? '#f59e0b' : 'none'} color={email.is_starred ? '#f59e0b' : 'var(--text-muted)'} />
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
