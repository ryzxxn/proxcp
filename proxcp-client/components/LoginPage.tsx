'use client';

import React, { useState } from 'react';
import { Zap, Loader2, Mail, User, Shield } from 'lucide-react';
import { signInEmail, signUpEmail } from '@/lib/auth-client';
import { toast } from 'sonner';

export default function LoginPage() {
  const [isSignUp, setIsSignUp] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (isSignUp) {
        await signUpEmail(name, email, password);
        toast.success('Registration successful');
      } else {
        await signInEmail(email, password);
        toast.success('Access granted');
      }
    } catch (err: any) {
      const msg = err.message || (isSignUp ? 'Registration failed.' : 'Access denied.');
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen bg-black text-white flex flex-col overflow-hidden font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-10 py-8 border-b border-zinc-900 bg-black shrink-0">
        <h1 className="text-2xl font-bold tracking-tight italic uppercase">
          proxcp<span className="text-zinc-700">_v1.0</span>
        </h1>
        <button 
          onClick={() => setIsSignUp(!isSignUp)}
          className="text-xs font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
        >
          {isSignUp ? 'Return to Login' : 'Request Access'}
        </button>
      </header>

      <main className="flex-1 flex items-center justify-center p-6 overflow-y-auto">
        <div className="max-w-md w-full p-12 rounded-[40px] bg-zinc-950 border border-zinc-900 animate-fade-in-up my-auto relative shadow-2xl shadow-white/5">
          <div className="w-16 h-16 bg-white rounded-3xl flex items-center justify-center mb-10 mx-auto shadow-xl">
            <Shield className="w-8 h-8 text-black" />
          </div>
          
          <div className="text-center">
            <h1 className="text-4xl font-bold tracking-tight mb-2">
              {isSignUp ? 'System Init' : 'Auth Required'}
            </h1>
            <p className="text-zinc-500 mb-10 text-sm font-medium leading-relaxed">
              {isSignUp ? 'Initialize credentials for network access.' : 'Provide clearance to access secure management sector.'}
            </p>
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-8">
            <div className="space-y-6">
              {isSignUp && (
                <div className="space-y-2">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 ml-1">Identity Tag</label>
                  <div className="relative">
                    <input 
                      type="text" 
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full bg-black border border-zinc-900 rounded-2xl px-12 py-4 text-sm font-medium outline-none transition-all focus:border-white placeholder:text-zinc-800 shadow-inner" 
                      placeholder="User name" 
                      required={isSignUp}
                    />
                    <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-700" />
                  </div>
                </div>
              )}
              <div className="space-y-2">
                <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 ml-1">Comms Address</label>
                <div className="relative">
                  <input 
                    type="email" 
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-black border border-zinc-900 rounded-2xl px-12 py-4 text-sm font-medium outline-none transition-all focus:border-white placeholder:text-zinc-800 shadow-inner" 
                    placeholder="name@sector.com" 
                    required
                  />
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-700" />
                </div>
              </div>
              <div className="space-y-2">
                <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 ml-1">Access Key</label>
                <div className="relative">
                  <input 
                    type="password" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-black border border-zinc-900 rounded-2xl px-12 py-4 text-sm font-medium outline-none transition-all focus:border-white placeholder:text-zinc-800 shadow-inner" 
                    placeholder="••••••••" 
                    required
                  />
                  <Zap className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-700" />
                </div>
              </div>
            </div>

            {error && (
              <div className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl text-xs font-bold text-zinc-400 flex items-center gap-3">
                <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
                {error}
              </div>
            )}

            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-white text-black py-5 rounded-2xl font-bold uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all flex items-center justify-center gap-4 group disabled:opacity-50 shadow-lg shadow-white/5"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  {isSignUp ? 'Initialize Access' : 'Confirm Clearance'}
                </>
              )}
            </button>
          </form>
        </div>
      </main>

      <footer className="p-10 border-t border-zinc-900 bg-black text-[10px] font-bold uppercase tracking-widest text-zinc-800 flex justify-between">
        <span>Sector_7G</span>
        <span>Secure Data Transmission Active</span>
      </footer>
    </div>
  );
}
