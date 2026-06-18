import React, { useState } from 'react';
import { login } from '../api';

type Step = 'phone' | 'code' | 'password' | 'done';

interface Props {
  onConnected: () => void;
}

export default function LoginPage({ onConnected }: Props) {
  const [step, setStep] = useState<Step>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      let payload: Record<string, string> = {};
      if (step === 'phone') payload = { phone };
      else if (step === 'code') payload = { phone, code };
      else if (step === 'password') payload = { phone, code, password };

      const res = await login(payload);
      const data = res.data;

      if (data.status === 'code_required') {
        setStep('code');
      } else if (data.status === 'password_required') {
        setStep('password');
      } else if (data.status === 'connected') {
        onConnected();
      } else {
        setError(data.message || 'خطای ناشناخته');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'خطا در اتصال');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0f2027] via-[#203a43] to-[#2c5364] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 shadow-2xl mb-4">
            <svg className="w-10 h-10 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8l-1.68 7.92c-.12.56-.46.7-.93.44l-2.57-1.89-1.24 1.19c-.14.14-.25.25-.51.25l.18-2.6 4.7-4.24c.2-.18-.04-.28-.32-.1L7.62 14.5l-2.52-.79c-.55-.17-.56-.55.12-.81l9.84-3.8c.46-.17.86.11.58.7z"/>
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white">تلگرام پنل</h1>
          <p className="text-blue-300 mt-1">مدیریت پیام‌های خصوصی</p>
        </div>

        {/* Card */}
        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-8 shadow-2xl border border-white/20">
          <div className="mb-6">
            {/* Steps */}
            <div className="flex items-center justify-center gap-2 mb-6">
              {['phone', 'code', 'password'].map((s, i) => (
                <React.Fragment key={s}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                    step === s ? 'bg-blue-500 text-white scale-110' :
                    ['phone', 'code', 'password'].indexOf(step) > i ? 'bg-green-500 text-white' :
                    'bg-white/20 text-white/50'
                  }`}>
                    {['phone', 'code', 'password'].indexOf(step) > i ? '✓' : i + 1}
                  </div>
                  {i < 2 && <div className={`h-0.5 w-8 ${['phone', 'code', 'password'].indexOf(step) > i ? 'bg-green-500' : 'bg-white/20'}`} />}
                </React.Fragment>
              ))}
            </div>

            <h2 className="text-white text-xl font-semibold text-center">
              {step === 'phone' && 'شماره تلفن'}
              {step === 'code' && 'کد تأیید'}
              {step === 'password' && 'رمز دو مرحله‌ای'}
            </h2>
            <p className="text-blue-200 text-sm text-center mt-1">
              {step === 'phone' && 'شماره تلگرام خود را وارد کنید'}
              {step === 'code' && `کد ارسال شده به ${phone} را وارد کنید`}
              {step === 'password' && 'رمز دو مرحله‌ای حساب خود را وارد کنید'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {step === 'phone' && (
              <div>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="+989123456789"
                  className="w-full bg-white/10 border border-white/30 rounded-xl px-4 py-3 text-white placeholder-white/40 focus:outline-none focus:border-blue-400 focus:bg-white/15 transition-all text-center text-lg tracking-widest"
                  dir="ltr"
                  required
                />
              </div>
            )}
            {step === 'code' && (
              <div>
                <input
                  type="text"
                  value={code}
                  onChange={e => setCode(e.target.value)}
                  placeholder="12345"
                  className="w-full bg-white/10 border border-white/30 rounded-xl px-4 py-3 text-white placeholder-white/40 focus:outline-none focus:border-blue-400 focus:bg-white/15 transition-all text-center text-2xl tracking-[0.5em] font-mono"
                  dir="ltr"
                  maxLength={8}
                  required
                />
              </div>
            )}
            {step === 'password' && (
              <div>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="رمز عبور"
                  className="w-full bg-white/10 border border-white/30 rounded-xl px-4 py-3 text-white placeholder-white/40 focus:outline-none focus:border-blue-400 focus:bg-white/15 transition-all text-center"
                  required
                />
              </div>
            )}

            {error && (
              <div className="bg-red-500/20 border border-red-400/30 rounded-xl px-4 py-3 text-red-300 text-sm text-center">
                ⚠️ {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-all shadow-lg hover:shadow-blue-500/30 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>در حال پردازش...</span>
                </>
              ) : (
                <span>
                  {step === 'phone' && 'ارسال کد'}
                  {step === 'code' && 'تأیید کد'}
                  {step === 'password' && 'ورود'}
                </span>
              )}
            </button>

            {step !== 'phone' && (
              <button
                type="button"
                onClick={() => { setStep('phone'); setCode(''); setPassword(''); setError(''); }}
                className="w-full text-blue-300 hover:text-white text-sm py-2 transition-colors"
              >
                ← بازگشت
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
