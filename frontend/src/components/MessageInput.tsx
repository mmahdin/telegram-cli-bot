import { useState, useRef, useEffect, useCallback } from 'react';
import type { ClipboardEvent, DragEvent, KeyboardEvent } from 'react';

interface Props {
  onSendText: (text: string) => Promise<void>;
  onSendPhoto: (file: File, caption: string) => Promise<void>;
  onSendAudio: (file: File, caption: string) => Promise<void>;
  onEditSubmit?: (newText: string) => Promise<void>;
  editingText?: string;
  onCancelEdit?: () => void;
}

export default function MessageInput({
  onSendText, onSendPhoto, onSendAudio, onEditSubmit, editingText, onCancelEdit
}: Props) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileCaption, setFileCaption] = useState('');
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [fileType, setFileType] = useState<'photo' | 'audio' | null>(null);
  const [showAttach, setShowAttach] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const textRef = useRef<HTMLTextAreaElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);

  // When editing, populate text
  useEffect(() => {
    if (editingText !== undefined) {
      setText(editingText);
      textRef.current?.focus();
    }
  }, [editingText]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }, [text]);

  const handleSend = async () => {
    if (sending) return;

    if (selectedFile) {
      setSending(true);
      try {
        if (fileType === 'photo') {
          await onSendPhoto(selectedFile, fileCaption);
        } else if (fileType === 'audio') {
          await onSendAudio(selectedFile, fileCaption);
        }
        clearFile();
      } finally {
        setSending(false);
      }
      return;
    }

    const trimmed = text.trim();
    if (!trimmed) return;

    setSending(true);
    try {
      if (onEditSubmit) {
        await onEditSubmit(trimmed);
        setText('');
      } else {
        await onSendText(trimmed);
        setText('');
      }
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const processFile = (file: File) => {
    const isImage = file.type.startsWith('image/');
    const isAudio = file.type.startsWith('audio/') || /\.(mp3|ogg|wav|flac|aac|m4a)$/i.test(file.name);

    if (isImage) {
      setFileType('photo');
      const reader = new FileReader();
      reader.onload = e => setFilePreview(e.target?.result as string);
      reader.readAsDataURL(file);
    } else if (isAudio) {
      setFileType('audio');
      setFilePreview(null);
    } else {
      alert('فقط فایل‌های عکس یا صدا قابل ارسال هستند');
      return;
    }
    setSelectedFile(file);
    setShowAttach(false);
  };

  const clearFile = () => {
    setSelectedFile(null);
    setFilePreview(null);
    setFileCaption('');
    setFileType(null);
  };

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  }, []);

  const handlePaste = useCallback((e: ClipboardEvent) => {
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (file) processFile(file);
        e.preventDefault();
        return;
      }
    }
  }, []);

  const isEditing = !!onEditSubmit;

  return (
    <div
      className={`rounded-2xl border transition-all ${
        dragOver
          ? 'border-blue-500 bg-blue-500/10'
          : isEditing
          ? 'border-yellow-500/30 bg-yellow-500/5'
          : 'border-white/10 bg-[#1e2536]'
      }`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* File preview */}
      {selectedFile && (
        <div className="px-3 pt-3 flex items-start gap-3">
          <div className="flex-1">
            {fileType === 'photo' && filePreview && (
              <img src={filePreview} alt="preview" className="max-h-32 rounded-lg object-contain" />
            )}
            {fileType === 'audio' && (
              <div className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2">
                <svg className="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                </svg>
                <span className="text-white/70 text-sm truncate">{selectedFile.name}</span>
                <span className="text-white/40 text-xs">{(selectedFile.size / 1024).toFixed(0)} KB</span>
              </div>
            )}
            <input
              type="text"
              value={fileCaption}
              onChange={e => setFileCaption(e.target.value)}
              placeholder="کپشن (اختیاری)"
              className="mt-2 w-full bg-transparent text-white/70 text-sm placeholder-white/30 focus:outline-none"
            />
          </div>
          <button
            onClick={clearFile}
            className="text-white/30 hover:text-white/60 p-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Drag overlay hint */}
      {dragOver && (
        <div className="px-4 py-3 text-center text-blue-300 text-sm">
          📎 رها کنید تا فایل ارسال شود
        </div>
      )}

      {/* Text area */}
      {!selectedFile && (
        <div className="flex items-end gap-2 px-3 py-2">
          {/* Attach button */}
          <div className="relative">
            <button
              onClick={() => setShowAttach(p => !p)}
              className="p-2 rounded-xl text-white/40 hover:text-white hover:bg-white/10 transition-all flex-shrink-0"
              title="پیوست"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>

            {showAttach && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowAttach(false)} />
                <div className="absolute bottom-12 left-0 z-20 bg-[#1e2536] border border-white/10 rounded-xl shadow-2xl overflow-hidden">
                  <button
                    onClick={() => { photoInputRef.current?.click(); setShowAttach(false); }}
                    className="flex items-center gap-2 px-4 py-3 text-sm text-white hover:bg-white/10 transition-colors w-full"
                  >
                    <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    ارسال عکس
                  </button>
                  <button
                    onClick={() => { audioInputRef.current?.click(); setShowAttach(false); }}
                    className="flex items-center gap-2 px-4 py-3 text-sm text-white hover:bg-white/10 transition-colors w-full"
                  >
                    <svg className="w-4 h-4 text-purple-400" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                    </svg>
                    ارسال آهنگ
                  </button>
                </div>
              </>
            )}
          </div>

          <textarea
            ref={textRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={isEditing ? 'ویرایش پیام...' : 'پیام بنویسید... (Shift+Enter برای خط جدید)'}
            rows={1}
            className="flex-1 bg-transparent text-white placeholder-white/30 text-sm focus:outline-none resize-none leading-relaxed py-1"
            style={{ direction: 'rtl' }}
          />

          {/* Cancel edit button */}
          {isEditing && (
            <button
              onClick={onCancelEdit}
              className="p-2 rounded-xl text-yellow-400/60 hover:text-yellow-400 hover:bg-yellow-400/10 transition-all flex-shrink-0"
              title="انصراف از ویرایش"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={sending || (!text.trim() && !selectedFile)}
            className={`p-2 rounded-xl flex-shrink-0 transition-all ${
              isEditing
                ? 'bg-yellow-500 hover:bg-yellow-600 disabled:opacity-40 text-white'
                : 'bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white'
            }`}
            title={isEditing ? 'ذخیره ویرایش' : 'ارسال'}
          >
            {sending ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : isEditing ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
              </svg>
            )}
          </button>
        </div>
      )}

      {/* File send button */}
      {selectedFile && (
        <div className="px-3 pb-3 flex justify-end">
          <button
            onClick={handleSend}
            disabled={sending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-all"
          >
            {sending ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                در حال ارسال...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
                ارسال {fileType === 'photo' ? 'عکس' : 'آهنگ'}
              </>
            )}
          </button>
        </div>
      )}

      {/* Hidden file inputs */}
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) processFile(f); e.target.value = ''; }}
      />
      <input
        ref={audioInputRef}
        type="file"
        accept="audio/*,.mp3,.ogg,.wav,.flac,.aac,.m4a"
        className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) processFile(f); e.target.value = ''; }}
      />
    </div>
  );
}
