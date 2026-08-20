import React, { useState, useRef, useEffect } from 'react';
import {
  Mail,
  Calendar,
  Star,
  Bookmark,
  CheckCheck,
  Clock,
  Eye,
  EyeOff,
  Reply,
  ReplyAll,
  Forward,
  Send,
  Trash2,
  Paperclip,
  Bold,
  Italic,
  Underline,
  Strikethrough,
  List,
  ListOrdered,
  Indent,
  Outdent,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Quote,
  RemoveFormatting,
  Type,
  Palette,
  Image,
  Link as LinkIcon,
  Smile,
  MoreVertical,
  Maximize2,
  Minimize2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  X
} from 'lucide-react';
import { format } from 'date-fns';
import { api } from '../api';

function ThreadMessageItem({ msg }) {
  const iframeRef = useRef(null);
  const [iframeHeight, setIframeHeight] = useState('350px');

  const updateIframeHeight = () => {
    try {
      if (!iframeRef.current) return;
      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc) return;

      const body = doc.body;
      const html = doc.documentElement;
      
      const computedHeight = Math.max(
        body ? body.scrollHeight : 0,
        body ? body.offsetHeight : 0,
        html ? html.clientHeight : 0,
        html ? html.scrollHeight : 0,
        html ? html.offsetHeight : 0
      );

      if (computedHeight > 0) {
        setIframeHeight(`${computedHeight + 24}px`);
      }
    } catch (err) {}
  };

  const handleIframeLoad = () => {
    updateIframeHeight();
    try {
      if (!iframeRef.current) return;
      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc) return;

      if (doc.body && typeof ResizeObserver !== 'undefined') {
        const resizeObserver = new ResizeObserver(() => updateIframeHeight());
        resizeObserver.observe(doc.body);
      }

      const imgs = doc.getElementsByTagName('img');
      for (let i = 0; i < imgs.length; i++) {
        if (!imgs[i].complete) {
          imgs[i].addEventListener('load', updateIframeHeight);
          imgs[i].addEventListener('error', updateIframeHeight);
        }
      }
    } catch (err) {}
  };

  useEffect(() => {
    setIframeHeight('350px');
    const timer = setTimeout(() => updateIframeHeight(), 150);
    return () => clearTimeout(timer);
  }, [msg.id, msg.html_body]);

  const senderInitial = (msg.sender || 'U').replace(/<.*>/, '').trim().charAt(0).toUpperCase() || 'U';
  
  let formattedDate = msg.received_at;
  try {
    let dateStr = msg.received_at;
    if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
      dateStr = dateStr + 'Z';
    }
    formattedDate = format(new Date(dateStr), 'EEEE, MMMM d, yyyy @ h:mm a');
  } catch (e) {}

  const isSentByMe = msg.sender.toLowerCase().includes('me <') ||
                     msg.sender.startsWith('Me ') ||
                     (msg.account_email && msg.sender.toLowerCase().includes(msg.account_email.toLowerCase()));

  const senderDisplayName = isSentByMe ? `Me <${msg.account_email || 'You'}>` : msg.sender;

  return (
    <div style={{
      border: '1px solid #e2e8f0',
      borderRadius: '12px',
      marginBottom: '16px',
      background: '#ffffff',
      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
      overflow: 'hidden'
    }}>
      <div style={{
        padding: '12px 20px',
        background: isSentByMe ? '#eef2ff' : '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            className="sender-avatar-md"
            style={isSentByMe ? { background: 'linear-gradient(135deg, #6366f1, #4f46e5)' } : {}}
          >
            {isSentByMe ? 'M' : senderInitial}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>{senderDisplayName}</span>
              {isSentByMe && (
                <span style={{ fontSize: '11px', fontWeight: 700, background: '#4f46e5', color: 'white', padding: '1px 6px', borderRadius: '4px' }}>
                  Sent Reply
                </span>
              )}
            </div>
            <span style={{ fontSize: '11.5px', color: '#64748b' }}>To: {msg.recipient || (isSentByMe ? 'Recipient' : 'Me')}</span>
          </div>
        </div>

        <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Calendar size={14} />
          <span>{formattedDate}</span>
        </div>
      </div>

      <div className="iframe-container" style={{ padding: '8px 0', minHeight: '150px' }}>
        <iframe
          ref={iframeRef}
          title={`Email Message ${msg.id}`}
          className="email-iframe"
          srcDoc={msg.html_body}
          onLoad={handleIframeLoad}
          style={{ height: iframeHeight, minHeight: '200px', width: '100%', border: 'none' }}
          sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
        />
      </div>

      {msg.attachments && msg.attachments.length > 0 && (
        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', fontSize: '12px', fontWeight: 700, color: '#334155' }}>
            <Paperclip size={14} color="#4f46e5" />
            <span>Attachments ({msg.attachments.length})</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {msg.attachments.map((att) => (
              <div
                key={att.id}
                onClick={async () => {
                  try {
                    await api.downloadAttachment(msg.id, att.id, att.filename);
                  } catch (err) {
                    alert('Download failed: ' + err.message);
                  }
                }}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '12px' }}
              >
                <Paperclip size={14} color="#6366f1" />
                <span>{att.filename}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function EmailDetail({
  email,
  onToggleStar,
  onToggleRead,
  onChangeFolderStatus,
  onRefresh
}) {
  const [composerMode, setComposerMode] = useState(null); // null, 'reply', 'reply_all', 'forward'
  const [toField, setToField] = useState('');
  const [ccField, setCcField] = useState('');
  const [bccField, setBccField] = useState('');
  const [subjectField, setSubjectField] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);
  
  const [showFormatToolbar, setShowFormatToolbar] = useState(true);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showKebabMenu, setShowKebabMenu] = useState(false);
  const [showScheduleDropdown, setShowScheduleDropdown] = useState(false);
  const [isPlainTextMode, setIsPlainTextMode] = useState(false);
  
  const [isPopout, setIsPopout] = useState(false);
  const [isQuotedCollapsed, setIsQuotedCollapsed] = useState(true);

  const [bodyText, setBodyText] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [draftSavedToast, setDraftSavedToast] = useState(false);

  const editorRef = useRef(null);
  const fileInputRef = useRef(null);
  const photoInputRef = useRef(null);
  const iframeRef = useRef(null);
  const [iframeHeight, setIframeHeight] = useState('600px');

  const updateIframeHeight = () => {
    try {
      if (!iframeRef.current) return;
      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc) return;

      const body = doc.body;
      const html = doc.documentElement;
      
      const computedHeight = Math.max(
        body ? body.scrollHeight : 0,
        body ? body.offsetHeight : 0,
        html ? html.clientHeight : 0,
        html ? html.scrollHeight : 0,
        html ? html.offsetHeight : 0
      );

      if (computedHeight > 0) {
        setIframeHeight(`${computedHeight + 24}px`);
      }
    } catch (err) {
      // Silent fallback
    }
  };

  const handleIframeLoad = () => {
    updateIframeHeight();
    
    try {
      if (!iframeRef.current) return;
      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc) return;

      if (doc.body && typeof ResizeObserver !== 'undefined') {
        const resizeObserver = new ResizeObserver(() => {
          updateIframeHeight();
        });
        resizeObserver.observe(doc.body);
      }

      const imgs = doc.getElementsByTagName('img');
      for (let i = 0; i < imgs.length; i++) {
        if (!imgs[i].complete) {
          imgs[i].addEventListener('load', updateIframeHeight);
          imgs[i].addEventListener('error', updateIframeHeight);
        }
      }
    } catch (err) {
      // Silent fallback
    }
  };

  // Reset composer state whenever the selected email ID changes
  useEffect(() => {
    setComposerMode(null);
    setToField('');
    setCcField('');
    setBccField('');
    setSubjectField('');
    setBodyText('');
    setAttachments([]);
    setErrorMsg('');
    setIsPopout(false);
    setIframeHeight('600px');

    const timer = setTimeout(() => {
      updateIframeHeight();
    }, 150);
    return () => clearTimeout(timer);
  }, [email?.id]);

  // Auto-save draft to localStorage every 3 seconds
  useEffect(() => {
    if (!email || !composerMode) return;
    const draftKey = `omnimail_draft_${email.id}`;
    let toastTimeout;

    const timer = setInterval(() => {
      const currentHtml = editorRef.current ? editorRef.current.innerHTML : bodyText;
      if (currentHtml && currentHtml.trim() && currentHtml !== '<br>') {
        localStorage.setItem(draftKey, JSON.stringify({
          composerMode,
          toField,
          ccField,
          bccField,
          subjectField,
          bodyHtml: currentHtml,
          updatedAt: new Date().toISOString()
        }));
        setDraftSavedToast(true);
        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => setDraftSavedToast(false), 2000);
      }
    }, 3000);

    return () => {
      clearInterval(timer);
      if (toastTimeout) clearTimeout(toastTimeout);
    };
  }, [email, composerMode, toField, ccField, bccField, subjectField, bodyText]);

  // Keyboard shortcut listener: Ctrl+Enter / Cmd+Enter to send, Escape to discard
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!composerMode) return;
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSend();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handlePromptDiscard();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [composerMode, toField, ccField, bccField, bodyText]);

  if (!email) {
    return (
      <div className="email-detail-pane">
        <div className="empty-state">
          <div className="empty-icon-large">
            <Mail size={44} />
          </div>
          <h3 className="empty-title">Select an Email Thread</h3>
          <p className="empty-subtitle">
            Choose a message from the conversation list to view its complete original HTML content preserved exactly as received from Gmail.
          </p>
        </div>
      </div>
    );
  }

  const senderInitial = (email.sender || 'U').replace(/<.*>/, '').trim().charAt(0).toUpperCase() || 'U';
  
  let formattedDate = email.received_at;
  try {
    let dateStr = email.received_at;
    if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
      dateStr = dateStr + 'Z';
    }
    formattedDate = format(new Date(dateStr), 'EEEE, MMMM d, yyyy @ h:mm a');
  } catch (e) {
    // Keep raw date string
  }

  const gmailDeepLink = `https://mail.google.com/mail/?authuser=${encodeURIComponent(email.account_email)}#inbox/${email.gmail_message_id}`;

  const handleStartReply = (mode) => {
    setComposerMode(mode);
    setErrorMsg('');
    setAttachments([]);
    
    // Check if draft exists in localStorage
    const draftKey = `omnimail_draft_${email.id}`;
    const savedDraftStr = localStorage.getItem(draftKey);
    let loadedBody = '';

    if (savedDraftStr) {
      try {
        const savedDraft = JSON.parse(savedDraftStr);
        loadedBody = savedDraft.bodyHtml || '';
      } catch (e) {}
    }

    setBodyText(loadedBody);

    if (mode === 'reply') {
      setToField(email.sender);
      setSubjectField(email.subject ? `Re: ${email.subject.replace(/^re:\s*/i, '')}` : 'Re: ');
    } else if (mode === 'reply_all') {
      setToField(email.sender);
      setSubjectField(email.subject ? `Re: ${email.subject.replace(/^re:\s*/i, '')}` : 'Re: ');
    } else if (mode === 'forward') {
      setToField('');
      setSubjectField(email.subject ? `Fwd: ${email.subject.replace(/^fwd:\s*/i, '')}` : 'Fwd: ');
    }

    setTimeout(() => {
      if (editorRef.current && loadedBody) {
        editorRef.current.innerHTML = loadedBody;
      }
    }, 50);
  };

  const handlePromptDiscard = () => {
    const currentHtml = editorRef.current ? editorRef.current.innerHTML : bodyText;
    if (currentHtml && currentHtml.trim() && currentHtml !== '<br>') {
      if (window.confirm('Discard this draft?')) {
        handleCloseComposer();
      }
    } else {
      handleCloseComposer();
    }
  };

  const handleCloseComposer = () => {
    if (email) {
      localStorage.removeItem(`omnimail_draft_${email.id}`);
    }
    setComposerMode(null);
    setBodyText('');
    setAttachments([]);
    setErrorMsg('');
    setIsPopout(false);
  };

  const applyFormat = (command, value = null) => {
    document.execCommand(command, false, value);
    if (editorRef.current) {
      setBodyText(editorRef.current.innerHTML);
    }
  };

  const handleInsertLink = () => {
    const url = prompt('Enter the URL to link to:', 'https://');
    if (url) {
      applyFormat('createLink', url);
    }
  };

  const handleInsertEmoji = (emojiStr) => {
    applyFormat('insertText', emojiStr);
    setShowEmojiPicker(false);
  };

  const handleInlinePhotoUpload = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const imgHtml = `<img src="${ev.target.result}" alt="${file.name}" style="max-width: 100%; height: auto; border-radius: 8px; margin: 8px 0;" />`;
        applyFormat('insertHTML', imgHtml);
      };
      reader.readAsDataURL(file);
    });
  };

  const handleFileAttachment = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      if (file.size > 25 * 1024 * 1024) {
        alert(`File ${file.name} exceeds Gmail's 25MB attachment limit.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = (ev) => {
        setAttachments((prev) => [
          ...prev,
          {
            name: file.name,
            size: (file.size / 1024).toFixed(1) + ' KB',
            type: file.type,
            base64: ev.target.result
          }
        ]);
      };
      reader.readAsDataURL(file);
    });
  };

  const handleRemoveAttachment = (idx) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  const togglePlainTextMode = () => {
    if (!isPlainTextMode) {
      // Stripping HTML tags to plain text
      const rawText = editorRef.current ? editorRef.current.innerText : '';
      if (editorRef.current) editorRef.current.innerText = rawText;
      setIsPlainTextMode(true);
    } else {
      setIsPlainTextMode(false);
    }
    setShowKebabMenu(false);
  };

  const handleSend = async () => {
    let contentHtml = editorRef.current ? editorRef.current.innerHTML : bodyText;
    if (isPlainTextMode && editorRef.current) {
      contentHtml = `<pre style="font-family: monospace; white-space: pre-wrap;">${editorRef.current.innerText}</pre>`;
    }

    if (!contentHtml.trim() || contentHtml === '<br>') {
      setErrorMsg('Please write a message before sending.');
      return;
    }

    setIsSending(true);
    setErrorMsg('');

    try {
      if (composerMode === 'forward') {
        if (!toField.trim()) {
          setErrorMsg('Please enter a recipient email address to forward.');
          setIsSending(false);
          return;
        }
        await api.forwardEmail(email.id, {
          to: toField.trim(),
          body_html: contentHtml,
          cc: ccField.trim() || null,
          bcc: bccField.trim() || null
        });
      } else {
        await api.replyToEmail(email.id, {
          body_html: contentHtml,
          reply_all: composerMode === 'reply_all',
          cc: ccField.trim() || null,
          bcc: bccField.trim() || null
        });
      }

      handleCloseComposer();
      if (onRefresh) onRefresh();
    } catch (err) {
      setErrorMsg(err.message || 'Failed to send email reply');
    } finally {
      setIsSending(false);
    }
  };

  const colorPalette = [
    '#000000', '#434343', '#666666', '#999999', '#cccccc', '#ffffff',
    '#980000', '#ff0000', '#ff9900', '#ffff00', '#00ff00', '#00ffff',
    '#4a86e8', '#0000ff', '#9900ff', '#ff00ff', '#e6b8af', '#f4ccd0'
  ];

  const popularEmojis = ['😊', '👍', '❤️', '🎉', '🔥', '🚀', '🙏', '💡', '✅', '👏'];

  const messagesToRender = (email.threadMessages && email.threadMessages.length > 0)
    ? email.threadMessages
    : [email];

  return (
    <div className="email-detail-pane">
      {/* Thread Action Header */}
      <div className="email-detail-top-actions">
        <div className="action-buttons-group">
          <button
            className={`btn-action ${email.is_starred ? 'active-star' : ''}`}
            onClick={() => onToggleStar(email)}
            title={email.is_starred ? 'Unstar Message' : 'Star Message'}
          >
            <Star size={16} fill={email.is_starred ? '#f59e0b' : 'none'} color={email.is_starred ? '#f59e0b' : 'currentColor'} />
            <span>{email.is_starred ? 'Starred' : 'Star'}</span>
          </button>

          <button
            className="btn-action"
            onClick={() => onToggleRead(email)}
            title={email.is_read ? 'Mark as Unread' : 'Mark as Read'}
          >
            {email.is_read ? <EyeOff size={16} /> : <Eye size={16} />}
            <span>{email.is_read ? 'Mark Unread' : 'Mark Read'}</span>
          </button>

          <div className="divider-vertical" />

          {/* View in Gmail Action Button */}
          <a
            href={gmailDeepLink}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-action"
            title="Open thread directly in Google Gmail web app"
            style={{ textDecoration: 'none' }}
          >
            <ExternalLink size={16} color="#4f46e5" />
            <span style={{ color: '#4f46e5', fontWeight: 700 }}>View in Gmail</span>
          </a>

          <div className="divider-vertical" />

          {/* Folder Tagging Buttons */}
          <button
            className={`btn-action ${email.folder_status === 'follow_up' ? 'active-folder' : ''}`}
            onClick={() => onChangeFolderStatus(email, email.folder_status === 'follow_up' ? 'inbox' : 'follow_up')}
            title="Toggle Follow Up"
          >
            <Bookmark size={16} />
            <span>Follow Up</span>
          </button>

          <button
            className={`btn-action ${email.folder_status === 'replied' ? 'active-folder' : ''}`}
            onClick={() => onChangeFolderStatus(email, email.folder_status === 'replied' ? 'inbox' : 'replied')}
            title="Toggle Replied"
          >
            <CheckCheck size={16} />
            <span>Replied</span>
          </button>

          <button
            className={`btn-action ${email.folder_status === 'snoozed' ? 'active-folder' : ''}`}
            onClick={() => onChangeFolderStatus(email, email.folder_status === 'snoozed' ? 'inbox' : 'snoozed')}
            title="Toggle Snoozed"
          >
            <Clock size={16} />
            <span>Snooze</span>
          </button>
        </div>
      </div>

      {/* Header Info */}
      <div className="email-detail-header">
        <h2 className="email-detail-subject">{email.subject || '(No Subject)'}</h2>

        <div className="email-meta-row">
          <div className="email-meta-left">
            <span className="account-source">
              Thread in <strong>{email.account_email}</strong> ({messagesToRender.length} message{messagesToRender.length === 1 ? '' : 's'})
            </span>
          </div>
          <div className="email-meta-right">
            <Calendar size={14} />
            <span>{formattedDate}</span>
          </div>
        </div>
      </div>

      {/* Render all messages in the conversation thread chronologically */}
      <div style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto', background: '#f8fafc', padding: '20px 24px' }}>
        {messagesToRender.map((msg) => (
          <ThreadMessageItem key={msg.id} msg={msg} />
        ))}
      </div>


      {/* Inline Reply / Forward Controls Section */}
      <div className="inline-compose-wrapper" style={{ flexShrink: 0, borderTop: '1px solid var(--border-color)', background: '#ffffff', padding: '12px 24px', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {!composerMode ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="btn-action"
              onClick={() => handleStartReply('reply')}
              style={{ padding: '8px 16px', background: '#f1f5f9', fontWeight: 600 }}
            >
              <Reply size={16} />
              <span>Reply</span>
            </button>

            <button
              className="btn-action"
              onClick={() => handleStartReply('reply_all')}
              style={{ padding: '8px 16px', background: '#f1f5f9', fontWeight: 600 }}
            >
              <ReplyAll size={16} />
              <span>Reply All</span>
            </button>

            <button
              className="btn-action"
              onClick={() => handleStartReply('forward')}
              style={{ padding: '8px 16px', background: '#f1f5f9', fontWeight: 600 }}
            >
              <Forward size={16} />
              <span>Forward</span>
            </button>
          </div>
        ) : (
          <div
            className={`compose-box-container ${isPopout ? 'is-popout' : ''}`}
            style={isPopout ? {
              position: 'fixed',
              bottom: '20px',
              right: '30px',
              width: '640px',
              maxHeight: 'calc(100vh - 60px)',
              height: '560px',
              zIndex: 9999,
              border: '1px solid var(--border-color)',
              borderRadius: '16px',
              boxShadow: '0 25px 50px rgba(0, 0, 0, 0.25)',
              display: 'flex',
              flexDirection: 'column',
              background: '#ffffff',
              overflow: 'hidden'
            } : {
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.06)',
              maxHeight: 'calc(100vh - 290px)',
              minHeight: '180px',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              background: '#ffffff'
            }}
          >
            {/* Composer Header */}
            <div
              style={{
                flexShrink: 0,
                padding: '10px 16px',
                background: '#f8fafc',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13.5px', fontWeight: 700, color: '#0f172a' }}>
                {composerMode === 'forward' ? <Forward size={16} color="#4f46e5" /> : <Reply size={16} color="#4f46e5" />}
                <span>
                  {composerMode === 'reply' && `Replying to ${email.sender}`}
                  {composerMode === 'reply_all' && `Replying All to ${email.sender}`}
                  {composerMode === 'forward' && 'Forwarding Message'}
                </span>
                {draftSavedToast && (
                  <span style={{ fontSize: '11px', color: '#16a34a', fontStyle: 'italic', marginLeft: '6px' }}>
                    Draft saved
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  className="btn-icon"
                  onClick={() => setIsPopout(!isPopout)}
                  title={isPopout ? 'Inline view' : 'Pop-out full screen'}
                >
                  {isPopout ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button className="btn-icon" onClick={handlePromptDiscard} title="Discard">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Recipient Fields */}
            <div style={{ flexShrink: 0, padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: '8px', borderBottom: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', width: '36px' }}>To:</span>
                <input
                  type="text"
                  className="form-input"
                  style={{ padding: '6px 12px', fontSize: '13px' }}
                  value={toField}
                  onChange={(e) => setToField(e.target.value)}
                  placeholder="Recipient email address"
                  readOnly={composerMode !== 'forward'}
                />
                {!showCcBcc && (
                  <button
                    onClick={() => setShowCcBcc(true)}
                    style={{ background: 'transparent', border: 'none', color: '#4f46e5', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    Cc / Bcc
                  </button>
                )}
              </div>

              {showCcBcc && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', width: '36px' }}>Cc:</span>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '6px 12px', fontSize: '13px' }}
                      value={ccField}
                      onChange={(e) => setCcField(e.target.value)}
                      placeholder="Carbon copy recipients"
                    />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', width: '36px' }}>Bcc:</span>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '6px 12px', fontSize: '13px' }}
                      value={bccField}
                      onChange={(e) => setBccField(e.target.value)}
                      placeholder="Blind carbon copy recipients"
                    />
                  </div>
                </>
              )}

              {/* Subject line (editable in Forward mode) */}
              {composerMode === 'forward' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', width: '60px' }}>Subject:</span>
                  <input
                    type="text"
                    className="form-input"
                    style={{ padding: '6px 12px', fontSize: '13px' }}
                    value={subjectField}
                    onChange={(e) => setSubjectField(e.target.value)}
                    placeholder="Subject"
                  />
                </div>
              )}
            </div>

            {/* Error banner if any */}
            {errorMsg && (
              <div style={{ flexShrink: 0, padding: '8px 16px', background: '#fef2f2', color: '#dc2626', fontSize: '13px', borderBottom: '1px solid #fecaca' }}>
                {errorMsg}
              </div>
            )}

            {/* Scrollable Middle Content Container (Editor + Attachments + Quoted History) */}
            <div className="compose-inner-scrollable" style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              {/* Rich Text Editor Body */}
              <div
                ref={editorRef}
                contentEditable={!isPlainTextMode}
                style={{
                  flex: '1 1 0%',
                  minHeight: '60px',
                  padding: '12px 16px',
                  outline: 'none',
                  fontSize: '14px',
                  lineHeight: 1.5,
                  color: '#0f172a',
                  fontFamily: isPlainTextMode ? 'monospace' : 'inherit'
                }}
                onInput={(e) => setBodyText(e.currentTarget.innerHTML)}
              />

              {/* Attached files preview */}
              {attachments.length > 0 && (
                <div style={{ flexShrink: 0, padding: '8px 16px', display: 'flex', flexWrap: 'wrap', gap: '8px', borderTop: '1px solid var(--border-color)', background: '#f8fafc' }}>
                  {attachments.map((att, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 10px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '12px' }}>
                      <Paperclip size={12} color="#4f46e5" />
                      <span>{att.name} ({att.size})</span>
                      <button onClick={() => handleRemoveAttachment(i)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#ef4444' }}>
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Collapsible Quoted Original Message (Gmail "···" style) */}
              <div style={{ flexShrink: 0, borderTop: '1px solid var(--border-color)', background: '#f8fafc' }}>
                <div
                  onClick={() => setIsQuotedCollapsed(!isQuotedCollapsed)}
                  style={{ padding: '8px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px', color: '#64748b', fontWeight: 600 }}
                >
                  <span>On {formattedDate}, {email.sender} wrote:</span>
                  {isQuotedCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                </div>

                {!isQuotedCollapsed && (
                  <div style={{ padding: '12px 16px', fontSize: '12px', color: '#475569', borderTop: '1px solid var(--border-color)', maxHeight: '160px', overflowY: 'auto' }}>
                    <div dangerouslySetInnerHTML={{ __html: email.html_body }} />
                  </div>
                )}
              </div>
            </div>

            {/* Combined Pinned Bottom Toolbars Block (Formatting Row + Actions Row) */}
            <div style={{ flexShrink: 0, background: '#ffffff', borderTop: '1px solid var(--border-color)' }}>
              {/* Expanded Formatting Toolbar ("A" toggle) */}
              {showFormatToolbar && (
                <div style={{ padding: '6px 16px', background: '#f8fafc', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px' }}>
                  {/* Font Family Dropdown */}
                  <select
                  onChange={(e) => applyFormat('fontName', e.target.value)}
                  style={{ padding: '3px 6px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '12px', outline: 'none' }}
                >
                  <option value="Sans Serif">Sans Serif</option>
                  <option value="Serif">Serif</option>
                  <option value="Fixed Width">Fixed Width</option>
                  <option value="Wide">Wide</option>
                  <option value="Narrow">Narrow</option>
                  <option value="Comic Sans MS">Comic Sans</option>
                  <option value="Georgia">Georgia</option>
                  <option value="Trebuchet MS">Trebuchet MS</option>
                  <option value="Verdana">Verdana</option>
                </select>

                {/* Font Size Dropdown */}
                <select
                  onChange={(e) => applyFormat('fontSize', e.target.value)}
                  style={{ padding: '3px 6px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '12px', outline: 'none' }}
                >
                  <option value="1">Small</option>
                  <option value="3">Normal</option>
                  <option value="5">Large</option>
                  <option value="7">Huge</option>
                </select>

                <div className="divider-vertical" style={{ height: '16px' }} />

                <button className="btn-icon" onClick={() => applyFormat('bold')} title="Bold">
                  <Bold size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('italic')} title="Italic">
                  <Italic size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('underline')} title="Underline">
                  <Underline size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('strikeThrough')} title="Strikethrough">
                  <Strikethrough size={14} />
                </button>

                <div className="divider-vertical" style={{ height: '16px' }} />

                {/* Color Picker Toggle */}
                <div style={{ position: 'relative' }}>
                  <button className="btn-icon" onClick={() => setShowColorPicker(!showColorPicker)} title="Text Color">
                    <Palette size={14} color="#4f46e5" />
                  </button>
                  {showColorPicker && (
                    <div style={{ position: 'absolute', bottom: '28px', left: 0, background: '#ffffff', border: '1px solid #cbd5e1', padding: '8px', borderRadius: '8px', display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '4px', zIndex: 10, boxShadow: '0 10px 25px rgba(0,0,0,0.15)' }}>
                      {colorPalette.map((c) => (
                        <div
                          key={c}
                          onClick={() => { applyFormat('foreColor', c); setShowColorPicker(false); }}
                          style={{ width: '16px', height: '16px', background: c, border: '1px solid #cbd5e1', borderRadius: '3px', cursor: 'pointer' }}
                        />
                      ))}
                    </div>
                  )}
                </div>

                <div className="divider-vertical" style={{ height: '16px' }} />

                <button className="btn-icon" onClick={() => applyFormat('justifyLeft')} title="Align Left">
                  <AlignLeft size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('justifyCenter')} title="Align Center">
                  <AlignCenter size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('justifyRight')} title="Align Right">
                  <AlignRight size={14} />
                </button>

                <div className="divider-vertical" style={{ height: '16px' }} />

                <button className="btn-icon" onClick={() => applyFormat('insertUnorderedList')} title="Bulleted List">
                  <List size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('insertOrderedList')} title="Numbered List">
                  <ListOrdered size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('outdent')} title="Indent Left">
                  <Outdent size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('indent')} title="Indent Right">
                  <Indent size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('formatBlock', 'blockquote')} title="Quote">
                  <Quote size={14} />
                </button>
                <button className="btn-icon" onClick={() => applyFormat('removeFormat')} title="Clear Formatting">
                  <RemoveFormatting size={14} />
                </button>
              </div>
            )}

            {/* Bottom Actions Toolbar (Exact Gmail Icon Set) */}
            <div style={{ padding: '10px 16px', background: '#ffffff', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {/* Primary Blue Send Button with Dropdown Arrow */}
                <div style={{ display: 'inline-flex', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 2px 8px rgba(79, 70, 229, 0.25)' }}>
                  <button
                    className="btn-primary"
                    onClick={handleSend}
                    disabled={isSending}
                    style={{ borderRadius: '0', padding: '8px 16px', fontSize: '13.5px' }}
                  >
                    <Send size={14} />
                    <span>{isSending ? 'Sending...' : 'Send'}</span>
                  </button>

                  <button
                    onClick={() => setShowScheduleDropdown(!showScheduleDropdown)}
                    disabled={isSending}
                    style={{ background: '#4338ca', border: 'none', color: 'white', padding: '0 8px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                    title="Schedule send"
                  >
                    <ChevronDown size={12} />
                  </button>
                </div>

                {showScheduleDropdown && (
                  <div style={{ position: 'absolute', bottom: '50px', left: '16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '8px', boxShadow: '0 10px 25px rgba(0,0,0,0.15)', fontSize: '12.5px', zIndex: 10 }}>
                    <div style={{ padding: '6px 12px', cursor: 'pointer', fontWeight: 600 }} onClick={() => { alert('Schedule send: Tomorrow morning 8:00 AM'); setShowScheduleDropdown(false); }}>
                      Tomorrow morning (8:00 AM)
                    </div>
                    <div style={{ padding: '6px 12px', cursor: 'pointer', fontWeight: 600 }} onClick={() => { alert('Schedule send: Monday morning 8:00 AM'); setShowScheduleDropdown(false); }}>
                      Monday morning (8:00 AM)
                    </div>
                  </div>
                )}

                <div className="divider-vertical" style={{ height: '20px' }} />

                {/* Formatting "A" Toggle */}
                <button
                  className="btn-icon"
                  onClick={() => setShowFormatToolbar(!showFormatToolbar)}
                  title="Formatting options"
                  style={{ background: showFormatToolbar ? '#e0e7ff' : 'transparent' }}
                >
                  <Type size={16} color={showFormatToolbar ? '#4f46e5' : 'currentColor'} />
                </button>

                {/* Attach File (Paperclip) */}
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  multiple
                  onChange={handleFileAttachment}
                />
                <button className="btn-icon" onClick={() => fileInputRef.current?.click()} title="Attach files">
                  <Paperclip size={16} />
                </button>

                {/* Insert Link */}
                <button className="btn-icon" onClick={handleInsertLink} title="Insert link">
                  <LinkIcon size={16} />
                </button>

                {/* Insert Emoji */}
                <div style={{ position: 'relative' }}>
                  <button className="btn-icon" onClick={() => setShowEmojiPicker(!showEmojiPicker)} title="Insert emoji">
                    <Smile size={16} />
                  </button>

                  {showEmojiPicker && (
                    <div style={{ position: 'absolute', bottom: '32px', left: 0, background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '8px', display: 'flex', gap: '6px', zIndex: 10, boxShadow: '0 10px 25px rgba(0,0,0,0.15)' }}>
                      {popularEmojis.map((em) => (
                        <span key={em} onClick={() => handleInsertEmoji(em)} style={{ cursor: 'pointer', fontSize: '18px' }}>
                          {em}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Insert Photo (Inline image) */}
                <input
                  type="file"
                  ref={photoInputRef}
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={handleInlinePhotoUpload}
                />
                <button className="btn-icon" onClick={() => photoInputRef.current?.click()} title="Insert photo inline">
                  <Image size={16} />
                </button>

                {/* Kebab Menu */}
                <div style={{ position: 'relative' }}>
                  <button className="btn-icon" onClick={() => setShowKebabMenu(!showKebabMenu)} title="More options">
                    <MoreVertical size={16} />
                  </button>

                  {showKebabMenu && (
                    <div style={{ position: 'absolute', bottom: '32px', right: 0, background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '6px 0', minWidth: '150px', zIndex: 10, boxShadow: '0 10px 25px rgba(0,0,0,0.15)', fontSize: '13px' }}>
                      <div
                        style={{ padding: '6px 14px', cursor: 'pointer', fontWeight: 500, color: isPlainTextMode ? '#4f46e5' : '#0f172a' }}
                        onClick={togglePlainTextMode}
                      >
                        {isPlainTextMode ? '✓ Plain text mode' : 'Plain text mode'}
                      </div>
                      <div style={{ padding: '6px 14px', cursor: 'pointer' }} onClick={() => { window.print(); setShowKebabMenu(false); }}>
                        Print
                      </div>
                      <div style={{ padding: '6px 14px', cursor: 'pointer' }} onClick={() => { alert('Spelling check complete. No errors found.'); setShowKebabMenu(false); }}>
                        Check spelling
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Discard Draft Trash Button */}
              <button className="btn-icon" onClick={handlePromptDiscard} title="Discard draft">
                <Trash2 size={16} color="#ef4444" />
              </button>
            </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
