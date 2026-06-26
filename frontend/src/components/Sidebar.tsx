import { useState, useMemo } from 'react';
import { Dialog, Me } from '../types';
import { formatDistanceToNow } from 'date-fns';
import { absoluteUrl } from '../api';
import { faIR } from 'date-fns/locale';

interface Props {
  dialogs: Dialog[];
  selectedId: number | null;
  onSelect: (d: Dialog) => void;
  onToggleImportant: (d: Dialog) => void;
  me: Me | null;
  loading: boolean;
  onRefresh: () => void;
  onLogout: () => void;
}

type MainFilter = 'all' | 'private' | 'group';
type ImportanceFilter = 'all' | 'important' | 'other';

function Avatar({ name, src, size = 'md' }: { name: string; src?: string | null; size?: 'sm' | 'md' | 'lg' }) {
  const sizeClass = size === 'sm' ? 'w-8 h-8 text-xs' : size === 'lg' ? 'w-12 h-12 text-base' : 'w-10 h-10 text-sm';
  const colors = [
    'from-purple-400 to-purple-600',
    'from-blue-400 to-blue-600',
    'from-green-400 to-green-600',
    'from-pink-400 to-pink-600',
    'from-orange-400 to-orange-600',
    'from-teal-400 to-teal-600',
    'from-red-400 to-red-600',
    'from-indigo-400 to-indigo-600',
  ];
  const initial = (name || 'U').charAt(0).toUpperCase();
  const colorIndex = initial.charCodeAt(0) % colors.length;

  const imageSrc = absoluteUrl(src);
  if (imageSrc) {
    return <img src={imageSrc} alt={name} className={`${sizeClass} rounded-full object-cover flex-shrink-0`} loading="lazy" />;
  }
  return (
    <div className={`${sizeClass} rounded-full bg-gradient-to-br ${colors[colorIndex]} flex items-center justify-center text-white font-bold flex-shrink-0`}>
      {initial}
    </div>
  );
}

export { Avatar };

function dialogKind(dialog: Dialog) {
  if (dialog.is_group || dialog.chat_type === 'group') return 'group';
  if (dialog.is_bot || dialog.chat_type === 'bot') return 'bot';
  return 'private';
}

function isGroupDialog(dialog: Dialog) {
  return dialogKind(dialog) === 'group';
}

function matchesMainFilter(dialog: Dialog, filter: MainFilter) {
  if (filter === 'group') return isGroupDialog(dialog);
  if (filter === 'private') return !isGroupDialog(dialog);
  return true;
}

function matchesImportanceFilter(dialog: Dialog, filter: ImportanceFilter) {
  if (filter === 'important') return Boolean(dialog.is_important);
  if (filter === 'other') return !Boolean(dialog.is_important);
  return true;
}

export default function Sidebar({ dialogs, selectedId, onSelect, onToggleImportant, me, loading, onRefresh, onLogout }: Props) {
  const [search, setSearch] = useState('');
  const [showProfile, setShowProfile] = useState(false);
  const [mainFilter, setMainFilter] = useState<MainFilter>('all');
  const [importanceFilter, setImportanceFilter] = useState<ImportanceFilter>('all');

  const mainCounts = useMemo(() => {
    const groups = dialogs.filter(isGroupDialog).length;
    return {
      all: dialogs.length,
      private: dialogs.length - groups,
      group: groups,
    };
  }, [dialogs]);

  const scopedDialogs = useMemo(
    () => dialogs.filter(d => matchesMainFilter(d, mainFilter)),
    [dialogs, mainFilter],
  );

  const importanceCounts = useMemo(() => {
    const important = scopedDialogs.filter(d => Boolean(d.is_important)).length;
    return {
      all: scopedDialogs.length,
      important,
      other: scopedDialogs.length - important,
    };
  }, [scopedDialogs]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return scopedDialogs
      .filter(d => {
        if (mainFilter !== 'all' && !matchesImportanceFilter(d, importanceFilter)) return false;
        if (!q) return true;
        return (
          (d.name || '').toLowerCase().includes(q) ||
          (d.username || '').toLowerCase().includes(q) ||
          (d.phone || '').includes(q)
        );
      })
      .sort((a, b) => {
        if (mainFilter !== 'all' && importanceFilter === 'all') {
          const importantDiff = Number(Boolean(b.is_important)) - Number(Boolean(a.is_important));
          if (importantDiff !== 0) return importantDiff;
        }
        return 0;
      });
  }, [scopedDialogs, search, mainFilter, importanceFilter]);

  const formatTime = (iso: string | null) => {
    if (!iso) return '';
    try {
      return formatDistanceToNow(new Date(iso), { addSuffix: false, locale: faIR });
    } catch {
      return '';
    }
  };

  const selectMainFilter = (value: MainFilter) => {
    setMainFilter(value);
    setImportanceFilter('all');
  };

  const mainFilterButton = (value: MainFilter, label: string, count: number) => (
    <button
      key={value}
      onClick={() => selectMainFilter(value)}
      className={`flex-1 rounded-xl px-2 py-1.5 text-xs transition-all ${
        mainFilter === value
          ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20'
          : 'bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'
      }`}
    >
      {label} <span className="opacity-70">{count}</span>
    </button>
  );

  const importanceFilterButton = (value: ImportanceFilter, label: string, count: number) => (
    <button
      key={value}
      onClick={() => setImportanceFilter(value)}
      className={`flex-1 rounded-xl px-2 py-1.5 text-xs transition-all ${
        importanceFilter === value
          ? 'bg-yellow-500/90 text-white shadow-lg shadow-yellow-900/20'
          : 'bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'
      }`}
    >
      {label} <span className="opacity-70">{count}</span>
    </button>
  );

  return (
    <div className="flex flex-col h-full bg-[#1a1f2e] border-r border-white/5">
      {/* Header */}
      <div className="px-4 py-3 bg-[#161b28] border-b border-white/5 flex items-center gap-3">
        <button
          onClick={() => setShowProfile(p => !p)}
          className="relative"
          title="پروفایل"
        >
          <Avatar name={me?.name || 'U'} src={me?.avatar} size="md" />
          <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-400 rounded-full border-2 border-[#161b28]" />
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm truncate">{me?.name || 'متصل شده'}</p>
          <p className="text-white/40 text-xs truncate">{me?.phone || ''}</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onRefresh}
            disabled={loading}
            title="بارگذاری مجدد"
            className="p-2 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-all"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <button
            onClick={onLogout}
            title="خروج"
            className="p-2 rounded-lg text-white/50 hover:text-red-400 hover:bg-red-400/10 transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>

      {/* Profile dropdown */}
      {showProfile && me && (
        <div className="mx-3 mt-2 mb-1 bg-white/5 rounded-xl p-3 border border-white/10">
          <div className="flex items-center gap-3">
            <Avatar name={me.name} src={me.avatar} size="lg" />
            <div className="min-w-0">
              <p className="text-white font-medium text-sm">{me.name}</p>
              {me.username && <p className="text-blue-300 text-xs">@{me.username}</p>}
              <p className="text-white/40 text-xs">{me.phone}</p>
            </div>
          </div>
        </div>
      )}

      {/* Search and filters */}
      <div className="px-3 py-2 space-y-2">
        <div className="relative">
          <svg className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="جستجو..."
            className="w-full bg-white/5 border border-white/10 rounded-xl py-2 pr-9 pl-3 text-white text-sm placeholder-white/30 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-all"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
            >×</button>
          )}
        </div>
        <div className="flex gap-1.5">
          {mainFilterButton('all', 'همه', mainCounts.all)}
          {mainFilterButton('private', 'شخصی', mainCounts.private)}
          {mainFilterButton('group', 'گروه‌ها', mainCounts.group)}
        </div>
        {mainFilter !== 'all' && (
          <div className="flex gap-1.5">
            {importanceFilterButton('all', 'همه', importanceCounts.all)}
            {importanceFilterButton('important', 'مهم', importanceCounts.important)}
            {importanceFilterButton('other', 'کم‌اهمیت', importanceCounts.other)}
          </div>
        )}
      </div>

      {/* Dialog list */}
      <div className="flex-1 overflow-y-auto">
        {loading && dialogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <div className="w-6 h-6 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
            <p className="text-white/30 text-sm">در حال بارگذاری...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-white/30">
            <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm">چتی یافت نشد</p>
          </div>
        ) : (
          filtered.map(dialog => (
            <button
              key={dialog.id}
              onClick={() => onSelect(dialog)}
              className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-all text-right border-b border-white/[0.03] ${
                selectedId === dialog.id ? 'bg-blue-600/20 border-l-2 border-l-blue-500' : ''
              }`}
            >
              <div className="relative flex-shrink-0">
                <Avatar name={dialog.name} src={dialog.avatar} />
                {dialog.is_important && (
                  <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-yellow-500 flex items-center justify-center">
                    <span className="text-white text-[8px] font-bold">★</span>
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-white text-sm font-medium truncate">{dialog.name}</span>
                  <span className="text-white/30 text-xs flex-shrink-0 mr-1">{formatTime(dialog.last_message_time)}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-white/40 text-xs truncate flex-1">
                    {dialog.last_message || 'بدون پیام'}
                  </p>
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(e) => { e.stopPropagation(); onToggleImportant(dialog); }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        e.stopPropagation();
                        onToggleImportant(dialog);
                      }
                    }}
                    className={`flex-shrink-0 mr-1 px-1.5 py-0.5 rounded-md text-xs transition-all ${
                      dialog.is_important
                        ? 'bg-yellow-400/20 text-yellow-300 hover:bg-yellow-400/30'
                        : 'bg-white/5 text-white/30 hover:bg-white/10 hover:text-white/60'
                    }`}
                    title={dialog.is_important ? 'حذف از مهم‌ها' : 'افزودن به مهم‌ها'}
                  >
                    ★
                  </span>
                  {dialog.unread_count > 0 && (
                    <span className="flex-shrink-0 mr-1 bg-blue-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center font-bold">
                      {dialog.unread_count > 99 ? '99+' : dialog.unread_count}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
