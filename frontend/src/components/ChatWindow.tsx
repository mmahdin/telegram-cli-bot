import { useState, useEffect, useRef, useCallback } from 'react';
import { Dialog, Message } from '../types';
import { Avatar } from './Sidebar';
import MessageBubble from './MessageBubble';
import MessageInput from './MessageInput';
import {
  getMessages,
  syncMessages,
  sendMessage,
  sendPhoto,
  sendAudio,
  editMessage,
  deleteMessage,
} from '../api';

interface Props {
  dialog: Dialog;
  onDialogRead?: () => void;
}

const PAGE_SIZE = 50;
const SYNC_PAGE_SIZE = 70;
const POLL_MS = 5000;

function orderOldToNew(messages: Message[]) {
  return [...messages].sort((a, b) => a.id - b.id);
}

function mergeMessages(current: Message[], incoming: Message[]) {
  const map = new Map<number, Message>();
  current.forEach(m => map.set(m.id, m));
  incoming.forEach(m => map.set(m.id, m));
  return orderOldToNew(Array.from(map.values()));
}

function dialogSubtitle(dialog: Dialog) {
  if (dialog.is_group || dialog.chat_type === 'group') return dialog.username ? `گروه · @${dialog.username}` : 'گروه تلگرام';
  if (dialog.is_bot || dialog.chat_type === 'bot') return dialog.username ? `ربات · @${dialog.username}` : 'ربات تلگرام';
  return dialog.username ? `@${dialog.username}` : dialog.phone || 'کاربر تلگرام';
}

export default function ChatWindow({ dialog, onDialogRead }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [initialLoading, setInitialLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [editingMsg, setEditingMsg] = useState<Message | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<Message | null>(null);
  const [error, setError] = useState('');

  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const syncRef = useRef(false);
  const olderRef = useRef(false);
  const mountedDialogRef = useRef(dialog.id);

  const isNearBottom = () => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  const scrollToBottom = (behavior: ScrollBehavior = 'auto') => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior }), 50);
  };

  const loadCache = useCallback(async (showLoading = false) => {
    if (showLoading) setInitialLoading(true);
    try {
      const res = await getMessages(dialog.id, PAGE_SIZE, 0, 0);
      const cached: Message[] = orderOldToNew(res.data.messages || []);
      if (mountedDialogRef.current !== dialog.id) return;
      setMessages(cached);
      setHasMore(cached.length >= PAGE_SIZE);
      setError('');
      scrollToBottom('auto');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در خواندن cache پیام‌ها');
    } finally {
      if (showLoading) setInitialLoading(false);
    }
  }, [dialog.id]);

  const syncLatest = useCallback(async (markRead = false) => {
    if (syncRef.current) return;
    syncRef.current = true;
    setSyncing(true);
    const shouldStickToBottom = isNearBottom();
    const afterId = messages.length ? messages[messages.length - 1].id : 0;

    try {
      const res = await syncMessages(dialog.id, SYNC_PAGE_SIZE, 0, afterId, markRead);
      const fresh: Message[] = orderOldToNew(res.data.messages || []);
      if (mountedDialogRef.current !== dialog.id) return;
      if (afterId > 0) {
        setMessages(prev => mergeMessages(prev, fresh));
      } else {
        setMessages(prev => mergeMessages(prev, fresh));
        if (fresh.length >= PAGE_SIZE) setHasMore(true);
      }
      setError('');
      if (shouldStickToBottom) scrollToBottom('smooth');
    } catch (e: any) {
      const status = e?.response?.status;
      if (status !== 401) {
        setError(e?.response?.data?.detail || e?.message || 'سینک پیام‌ها ناموفق بود');
      }
    } finally {
      syncRef.current = false;
      setSyncing(false);
    }
  }, [dialog.id, messages]);

  const loadOlder = useCallback(async () => {
    if (olderRef.current || !hasMore || messages.length === 0) return;
    olderRef.current = true;
    setLoadingMore(true);

    const oldestId = messages[0]?.id || 0;
    const container = containerRef.current;
    const prevScrollHeight = container?.scrollHeight || 0;

    const mergeAndKeepPosition = (older: Message[]) => {
      if (!older.length) return;
      setMessages(prev => mergeMessages(older, prev));
      setTimeout(() => {
        if (container) container.scrollTop = container.scrollHeight - prevScrollHeight;
      }, 50);
    };

    try {
      // First try local JSON cache. This is instant after history has been seen once.
      const cachedRes = await getMessages(dialog.id, PAGE_SIZE, oldestId, 0);
      const cachedOlder: Message[] = orderOldToNew(cachedRes.data.messages || []);
      mergeAndKeepPosition(cachedOlder);

      if (cachedOlder.length >= PAGE_SIZE) {
        setError('');
        return;
      }

      // If cache does not have enough older messages, fetch one older page from Telegram.
      const syncRes = await syncMessages(dialog.id, PAGE_SIZE, oldestId, 0, false);
      const syncedOlder: Message[] = orderOldToNew(syncRes.data.messages || []);
      if (syncedOlder.length < PAGE_SIZE) setHasMore(false);
      mergeAndKeepPosition(syncedOlder);
      setError('');
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 401) {
        setHasMore(false);
      } else {
        setError(e?.response?.data?.detail || e?.message || 'خطا در دریافت پیام‌های قدیمی‌تر');
      }
    } finally {
      olderRef.current = false;
      setLoadingMore(false);
    }
  }, [dialog.id, hasMore, messages]);

  useEffect(() => {
    mountedDialogRef.current = dialog.id;
    setMessages([]);
    setHasMore(true);
    setReplyTo(null);
    setEditingMsg(null);
    setDeleteConfirm(null);
    setError('');

    let cancelled = false;
    const runInitialLoad = async () => {
      await loadCache(true);
      if (cancelled) return;
      setSyncing(true);
      try {
        // Keep Telegram unread receipts private: initial panel sync must not mark messages as read in Telegram.
        const res = await syncMessages(dialog.id, SYNC_PAGE_SIZE, 0, 0, false);
        const fresh: Message[] = orderOldToNew(res.data.messages || []);
        if (!cancelled && mountedDialogRef.current === dialog.id) {
          setMessages(prev => mergeMessages(prev, fresh));
          setHasMore(fresh.length >= PAGE_SIZE);
          scrollToBottom('auto');
        }
      } catch (e: any) {
        const status = e?.response?.status;
        if (status !== 401 && !cancelled) {
          setError(e?.response?.data?.detail || e?.message || 'سینک اولیه پیام‌ها ناموفق بود');
        }
      } finally {
        if (!cancelled) setSyncing(false);
      }
    };

    runInitialLoad();
    onDialogRead?.();
    return () => { cancelled = true; };
  }, [dialog.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const timer = setInterval(() => syncLatest(false), POLL_MS);
    return () => clearInterval(timer);
  }, [syncLatest]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    if (container.scrollTop < 120) loadOlder();
  }, [loadOlder]);

  const handleSendText = async (text: string) => {
    try {
      const res = await sendMessage(dialog.id, text, replyTo?.id);
      const newMsg: Message = res.data.message;
      setMessages(prev => mergeMessages(prev, [newMsg]));
      setReplyTo(null);
      scrollToBottom('smooth');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در ارسال پیام');
    }
  };

  const handleSendPhoto = async (file: File, caption: string) => {
    try {
      const res = await sendPhoto(dialog.id, file, caption, replyTo?.id);
      const newMsg: Message = res.data.message;
      setMessages(prev => mergeMessages(prev, [newMsg]));
      setReplyTo(null);
      scrollToBottom('smooth');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در ارسال عکس');
    }
  };

  const handleSendAudio = async (file: File, caption: string) => {
    try {
      const res = await sendAudio(dialog.id, file, caption, replyTo?.id);
      const newMsg: Message = res.data.message;
      setMessages(prev => mergeMessages(prev, [newMsg]));
      setReplyTo(null);
      scrollToBottom('smooth');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در ارسال فایل صوتی');
    }
  };

  const handleEditSubmit = async (newText: string) => {
    if (!editingMsg) return;
    try {
      const res = await editMessage(dialog.id, editingMsg.id, newText);
      const updated: Message = res.data.message;
      setMessages(prev => mergeMessages(prev.filter(m => m.id !== updated.id), [updated]));
      setEditingMsg(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در ویرایش پیام');
    }
  };

  const handleDelete = async (msg: Message) => {
    try {
      await deleteMessage(dialog.id, msg.id);
      setMessages(prev => prev.filter(m => m.id !== msg.id));
      setDeleteConfirm(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'خطا در حذف پیام');
    }
  };

  const msgMap = new Map(messages.map(m => [m.id, m]));

  return (
    <div className="flex flex-col h-full bg-[#0f1623]">
      <div className="px-4 py-3 bg-[#161b28] border-b border-white/5 flex items-center gap-3 flex-shrink-0">
        <Avatar name={dialog.name} src={dialog.avatar} size="md" />
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm">{dialog.name}</p>
          <p className="text-white/40 text-xs">
            {dialogSubtitle(dialog)}
          </p>
        </div>
        {syncing && <span className="text-white/30 text-xs">سینک...</span>}
        <button
          onClick={() => syncLatest(true)}
          className="p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-all"
          title="سینک پیام‌های جدید"
        >
          <svg className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-2 bg-red-500/20 border border-red-400/30 rounded-xl px-4 py-2 text-red-300 text-sm flex items-center justify-between">
          <span>⚠️ {error}</span>
          <button onClick={() => setError('')} className="text-red-300/50 hover:text-red-300 ml-2">×</button>
        </div>
      )}

      <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5">
        {loadingMore && (
          <div className="flex justify-center py-2">
            <div className="w-5 h-5 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
          </div>
        )}
        {!hasMore && messages.length > 0 && <p className="text-center text-white/20 text-xs py-2">شروع مکالمه</p>}

        {initialLoading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="w-8 h-8 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
            <p className="text-white/30 text-sm">در حال خواندن cache پیام‌ها...</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-white/20">
            <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p>{syncing ? 'در حال سینک پیام‌ها...' : 'هنوز پیامی در cache نیست'}</p>
          </div>
        ) : (
          messages.map(msg => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onEdit={setEditingMsg}
              onDelete={setDeleteConfirm}
              onReply={setReplyTo}
              replyMessage={msg.reply_to_msg_id ? msgMap.get(msg.reply_to_msg_id) : null}
              showSender={dialog.is_group || dialog.chat_type === 'group'}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {(replyTo || editingMsg) && (
        <div className="mx-4 mb-2 flex items-center gap-2 bg-blue-600/20 border border-blue-500/30 rounded-xl px-3 py-2">
          <div className="flex-1 min-w-0">
            <p className="text-blue-400 text-xs font-medium mb-0.5">
              {editingMsg ? '✏️ ویرایش پیام' : `↩️ ریپلای به: ${replyTo?.is_outgoing ? 'شما' : (replyTo?.sender_name || dialog.name)}`}
            </p>
            <p className="text-white/60 text-xs truncate">{editingMsg?.text || replyTo?.text || '[media]'}</p>
          </div>
          <button onClick={() => { setReplyTo(null); setEditingMsg(null); }} className="text-white/40 hover:text-white transition-colors p-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      <div className="flex-shrink-0 px-4 pb-4">
        <MessageInput
          onSendText={handleSendText}
          onSendPhoto={handleSendPhoto}
          onSendAudio={handleSendAudio}
          onEditSubmit={editingMsg ? handleEditSubmit : undefined}
          editingText={editingMsg?.text}
          onCancelEdit={() => setEditingMsg(null)}
        />
      </div>

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#1e2536] border border-white/10 rounded-2xl p-6 w-80 shadow-2xl">
            <h3 className="text-white font-semibold text-lg mb-2">حذف پیام</h3>
            <p className="text-white/60 text-sm mb-4">آیا مطمئنید که می‌خواهید این پیام را حذف کنید؟</p>
            {deleteConfirm.text && <div className="bg-white/5 rounded-lg px-3 py-2 mb-4 text-white/50 text-sm line-clamp-3">{deleteConfirm.text}</div>}
            <div className="flex gap-2">
              <button onClick={() => setDeleteConfirm(null)} className="flex-1 py-2 rounded-xl border border-white/10 text-white/60 hover:text-white hover:border-white/20 transition-all text-sm">انصراف</button>
              <button onClick={() => handleDelete(deleteConfirm)} className="flex-1 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white font-medium transition-all text-sm">حذف</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

