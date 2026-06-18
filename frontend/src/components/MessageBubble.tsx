import { useState } from 'react';
import type { MouseEvent, TouchEvent } from 'react';
import { Message, MediaInfo } from '../types';
import { absoluteUrl } from '../api';
import { format } from 'date-fns';
import { faIR } from 'date-fns/locale';

interface Props {
  message: Message;
  onEdit: (msg: Message) => void;
  onDelete: (msg: Message) => void;
  onReply: (msg: Message) => void;
  replyMessage?: Message | null;
}

function formatBytes(size?: number | null) {
  if (!size || size <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function mediaIcon(type: MediaInfo['type']) {
  if (type === 'photo') return '🖼️';
  if (type === 'video') return '🎬';
  if (type === 'voice') return '🎙️';
  if (type === 'audio') return '🎵';
  return '📎';
}

function mediaTitle(media: MediaInfo) {
  if (media.filename) return media.filename;
  if (media.type === 'photo') return 'عکس';
  if (media.type === 'video') return 'ویدیو';
  if (media.type === 'voice') return 'ویس';
  if (media.type === 'audio') return 'فایل صوتی';
  return 'فایل';
}

function MediaRenderer({ media }: { media: MediaInfo }) {
  const mediaSrc = absoluteUrl(media.download_url);
  const size = formatBytes(media.size);

  return (
    <div className="min-w-[220px] max-w-[280px] rounded-xl border border-white/10 bg-black/15 px-3 py-2.5 flex items-center gap-3">
      <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-lg flex-shrink-0">
        {mediaIcon(media.type)}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-white/80 text-xs truncate" title={mediaTitle(media)}>
          {mediaTitle(media)}
        </p>
        <p className="text-white/35 text-[11px] truncate">
          {[media.mime, size].filter(Boolean).join(' • ') || 'برای مشاهده، دانلود کنید'}
        </p>
      </div>
      {mediaSrc ? (
        <a
          href={mediaSrc}
          download
          className="px-2.5 py-1.5 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-blue-200 text-xs transition-colors flex-shrink-0"
          title="دانلود فایل"
        >
          دانلود
        </a>
      ) : (
        <span className="text-white/30 text-xs">بدون لینک</span>
      )}
    </div>
  );
}

export default function MessageBubble({ message, onEdit, onDelete, onReply, replyMessage }: Props) {
  const [showMenu, setShowMenu] = useState(false);
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 });

  const isOut = message.is_outgoing;
  const timeStr = message.date
    ? format(new Date(message.date), 'HH:mm', { locale: faIR })
    : '';

  const handleContextMenu = (e: MouseEvent) => {
    e.preventDefault();
    setMenuPos({ x: e.clientX, y: e.clientY });
    setShowMenu(true);
  };

  const handleLongPress = (() => {
    let timer: ReturnType<typeof setTimeout>;
    return {
      onTouchStart: (e: TouchEvent) => {
        timer = setTimeout(() => {
          const touch = e.touches[0];
          setMenuPos({ x: touch.clientX, y: touch.clientY });
          setShowMenu(true);
        }, 600);
      },
      onTouchEnd: () => clearTimeout(timer),
    };
  })();

  return (
    <>
      <div
        className={`flex ${isOut ? 'justify-end' : 'justify-start'} mb-1 group`}
        onContextMenu={handleContextMenu}
        {...handleLongPress}
      >
        <div
          className={`relative max-w-[75%] px-3 py-2 rounded-2xl text-sm shadow-sm ${
            isOut
              ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-br-sm'
              : 'bg-[#2a3142] text-white rounded-bl-sm'
          }`}
        >
          {/* Reply */}
          {replyMessage && (
            <div className={`mb-1.5 px-2 py-1 rounded-lg border-r-2 text-xs ${isOut ? 'bg-blue-800/50 border-blue-300' : 'bg-white/10 border-blue-400'}`}>
              <p className="text-blue-300 font-medium mb-0.5">
                {replyMessage.is_outgoing ? 'شما' : 'پیام'}
              </p>
              <p className="text-white/70 line-clamp-2">{replyMessage.text || '[media]'}</p>
            </div>
          )}

          {/* Media: metadata only. No image/video/audio file is downloaded while rendering the chat. */}
          {message.media && <MediaRenderer media={message.media} />}

          {/* Text */}
          {message.text && (
            <p className="whitespace-pre-wrap break-words leading-relaxed mt-1">{message.text}</p>
          )}

          {/* Time & edited */}
          <div className={`flex items-center gap-1 mt-1 ${isOut ? 'justify-end' : 'justify-start'}`}>
            {message.edit_date && (
              <span className="text-white/40 text-[10px]">ویرایش شده</span>
            )}
            <span className="text-white/40 text-[10px]">{timeStr}</span>
            {isOut && (
              <svg className="w-3 h-3 text-blue-300" fill="currentColor" viewBox="0 0 16 16">
                <path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425z"/>
              </svg>
            )}
          </div>

          {/* Hover quick actions */}
          <div className={`absolute top-1 ${isOut ? 'left-1' : 'right-1'} opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5`}>
            <button
              onClick={(e) => { e.stopPropagation(); onReply(message); }}
              className="p-1 rounded-full bg-black/30 hover:bg-black/50 text-white/70 hover:text-white"
              title="ریپلای"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
            </button>
            {isOut && (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); onEdit(message); }}
                  className="p-1 rounded-full bg-black/30 hover:bg-black/50 text-white/70 hover:text-white"
                  title="ویرایش"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(message); }}
                  className="p-1 rounded-full bg-black/30 hover:bg-red-500/50 text-white/70 hover:text-red-300"
                  title="حذف"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Context Menu */}
      {showMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
          <div
            className="fixed z-50 bg-[#1e2536] border border-white/10 rounded-xl shadow-2xl py-1 min-w-[150px]"
            style={{ left: menuPos.x, top: menuPos.y, transform: 'translate(-50%, -50%)' }}
          >
            <button
              onClick={() => { onReply(message); setShowMenu(false); }}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-white hover:bg-white/10 transition-colors"
            >
              <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              ریپلای
            </button>
            {isOut && (
              <>
                <button
                  onClick={() => { onEdit(message); setShowMenu(false); }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-white hover:bg-white/10 transition-colors"
                >
                  <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  ویرایش
                </button>
                <div className="border-t border-white/5 my-1" />
                <button
                  onClick={() => { onDelete(message); setShowMenu(false); }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-400 hover:bg-red-400/10 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  حذف پیام
                </button>
              </>
            )}
          </div>
        </>
      )}
    </>
  );
}
