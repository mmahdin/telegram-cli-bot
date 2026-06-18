import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Dialog, Me, AuthStatus } from './types';
import {
  checkAuthStatus,
  connectExistingSession,
  getDialogs,
  syncDialogs,
  syncAvatars,
  markDialogRead,
  logout,
} from './api';
import LoginPage from './components/LoginPage';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';

const DIALOG_POLL_MS = 10000;

export default function App() {
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [authError, setAuthError] = useState('');
  const [dialogs, setDialogs] = useState<Dialog[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loadingDialogs, setLoadingDialogs] = useState(false);
  const syncInFlight = useRef(false);

  const selectedDialog = useMemo(
    () => dialogs.find(d => d.id === selectedId) || null,
    [dialogs, selectedId],
  );

  const fetchCachedDialogs = useCallback(async (showLoading = false) => {
    if (showLoading) setLoadingDialogs(true);
    try {
      const res = await getDialogs(100);
      setDialogs(res.data.dialogs || []);
      setAuthError('');
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'خطا در خواندن cache چت‌ها';
      setAuthError(String(detail));
    } finally {
      if (showLoading) setLoadingDialogs(false);
    }
  }, []);

  const syncDialogsInBackground = useCallback(async () => {
    if (!connected || syncInFlight.current) return;
    syncInFlight.current = true;
    try {
      const res = await syncDialogs(100);
      setDialogs(res.data.dialogs || []);
      setAuthError('');
      // Low-priority avatar worker. It does not block message/dialog rendering.
      syncAvatars(12).catch(() => {});
    } catch (e: any) {
      const status = e?.response?.status;
      if (status !== 401) {
        setAuthError(e?.response?.data?.detail || e?.message || 'سینک چت‌ها ناموفق بود');
      }
    } finally {
      syncInFlight.current = false;
      // Fetch cache once more; avatar files may have appeared meanwhile.
      fetchCachedDialogs(false).catch(() => {});
    }
  }, [connected, fetchCachedDialogs]);

  const checkAuth = useCallback(async (silent = false) => {
    if (!silent) setCheckingAuth(true);
    try {
      const res = await checkAuthStatus();
      const data = res.data as AuthStatus;
      setConnecting(Boolean(data.connecting));
      setAuthError(data.last_error || '');
      if (data.connected) {
        setConnected(true);
        setMe(data.me);
      } else {
        setConnected(false);
        setMe(null);
      }
    } catch (e: any) {
      setConnected(false);
      setConnecting(false);
      setMe(null);
      setAuthError(e?.message || 'بک‌اند در دسترس نیست');
    } finally {
      if (!silent) setCheckingAuth(false);
    }
  }, []);

  useEffect(() => {
    checkAuth(false);
  }, [checkAuth]);

  useEffect(() => {
    if (connected || !connecting) return;
    const timer = setInterval(() => checkAuth(true), 1500);
    return () => clearInterval(timer);
  }, [connected, connecting, checkAuth]);

  useEffect(() => {
    if (!connected) return;
    // First paint: JSON cache only. This should be instant.
    fetchCachedDialogs(true).then(() => syncDialogsInBackground());
    const timer = setInterval(() => syncDialogsInBackground(), DIALOG_POLL_MS);
    return () => clearInterval(timer);
  }, [connected, fetchCachedDialogs, syncDialogsInBackground]);

  const handleConnected = () => {
    setConnecting(true);
    checkAuth(false);
  };

  const handleTryConnectExistingSession = async () => {
    setConnecting(true);
    setAuthError('');
    try {
      await connectExistingSession();
    } catch (e: any) {
      setConnecting(false);
      setAuthError(e?.response?.data?.detail || e?.message || 'اتصال مجدد ناموفق بود');
    }
    checkAuth(true);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch {}
    setConnected(false);
    setConnecting(false);
    setMe(null);
    setDialogs([]);
    setSelectedId(null);
  };

  const handleSelectDialog = (dialog: Dialog) => {
    setSelectedId(dialog.id);
    // Optimistic local badge clear; backend persists it only to JSON by default.
    // It does not send Telegram read receipts, so the sender should not get a second tick.
    setDialogs(prev => prev.map(d => d.id === dialog.id ? { ...d, unread_count: 0 } : d));
    markDialogRead(dialog.id).catch(() => {});
  };

  const handleRefresh = () => {
    fetchCachedDialogs(true).then(() => syncDialogsInBackground());
  };

  if (checkingAuth || (!connected && connecting)) {
    return (
      <div className="min-h-screen bg-[#0f1623] flex items-center justify-center" dir="rtl">
        <div className="flex flex-col items-center gap-4 text-center px-6">
          <div className="w-12 h-12 border-3 border-blue-400/20 border-t-blue-400 rounded-full animate-spin" />
          <p className="text-white/50 text-sm">
            {connecting ? 'در حال اتصال به تلگرام...' : 'در حال بررسی اتصال...'}
          </p>
          {authError && (
            <div className="max-w-md bg-red-500/10 border border-red-400/20 text-red-300 rounded-xl px-4 py-3 text-xs leading-6">
              {authError}
              <button onClick={handleTryConnectExistingSession} className="block mx-auto mt-2 text-blue-300 hover:text-blue-200">
                تلاش دوباره
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!connected) {
    return <LoginPage onConnected={handleConnected} />;
  }

  return (
    <div className="min-h-screen bg-[#0f1623] flex" dir="rtl">
      <div className="w-80 flex-shrink-0 h-screen overflow-hidden">
        <Sidebar
          dialogs={dialogs}
          selectedId={selectedId}
          onSelect={handleSelectDialog}
          me={me}
          loading={loadingDialogs || syncInFlight.current}
          onRefresh={handleRefresh}
          onLogout={handleLogout}
        />
      </div>

      <div className="flex-1 h-screen overflow-hidden">
        {authError && dialogs.length === 0 ? (
          <PanelError message={authError} onRetry={handleRefresh} />
        ) : selectedDialog ? (
          <ChatWindow key={selectedDialog.id} dialog={selectedDialog} onDialogRead={() => handleSelectDialog(selectedDialog)} />
        ) : (
          <EmptyState dialogCount={dialogs.length} loading={loadingDialogs} />
        )}
      </div>
    </div>
  );
}

function PanelError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 text-center px-8">
      <div className="text-red-300 bg-red-500/10 border border-red-400/20 rounded-2xl px-5 py-4 max-w-lg text-sm leading-7">
        {message}
      </div>
      <button onClick={onRetry} className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm transition-colors">
        تلاش دوباره
      </button>
    </div>
  );
}

function EmptyState({ dialogCount, loading }: { dialogCount: number; loading: boolean }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-6 text-center px-8">
      <div className="relative">
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-500/20 to-blue-700/20 flex items-center justify-center border border-blue-500/20 animate-pulse">
          <svg className="w-12 h-12 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8l-1.68 7.92c-.12.56-.46.7-.93.44l-2.57-1.89-1.24 1.19c-.14.14-.25.25-.51.25l.18-2.6 4.7-4.24c.2-.18-.04-.28-.32-.1L7.62 14.5l-2.52-.79c-.55-.17-.56-.55.12-.81l9.84-3.8c.46-.17.86.11.58.7z"/>
          </svg>
        </div>
      </div>
      <div className="space-y-2">
        <h2 className="text-white text-2xl font-semibold">تلگرام پنل</h2>
        <p className="text-white/40 text-sm max-w-xs">
          {loading
            ? 'در حال خواندن cache و شروع سینک پس‌زمینه...'
            : dialogCount > 0
              ? 'یک مکالمه را انتخاب کنید'
              : 'هنوز cache چتی وجود ندارد. بعد از سینک تلگرام، چت‌ها اینجا می‌آیند'}
        </p>
      </div>
    </div>
  );
}
