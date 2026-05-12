import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  Server, 
  Wrench, 
  Key, 
  Settings, 
  LogOut,
  Zap,
  Moon,
  Sun
} from 'lucide-react';
import { authClient } from '@/lib/auth-client';
import { useRouter } from 'next/navigation';

const navItems = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Servers', href: '/servers', icon: Server },
  { name: 'Tools', href: '/tools', icon: Wrench },
  { name: 'Access Control', href: '/apikeys', icon: Key },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    await authClient.signOut();
    router.push('/login');
  };

  return (
    <aside className="w-20 lg:w-64 border-r border-zinc-900 bg-black flex flex-col h-full shrink-0 transition-all duration-300">
      <div className="p-4 lg:p-6 border-b border-zinc-900 flex items-center justify-center lg:justify-start gap-3 shrink-0">
        <span className="hidden lg:block text-xl font-bold tracking-tight text-white uppercase italic">proxcp</span>
      </div>

      <nav className="flex-1 p-2 lg:p-4 space-y-2 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center justify-center lg:justify-start gap-3 p-3 lg:px-4 lg:py-3 rounded-2xl text-[10px] font-bold uppercase tracking-widest transition-all ${
                isActive 
                  ? 'bg-white text-black shadow-lg shadow-white/5' 
                  : 'text-zinc-500 hover:bg-zinc-900 hover:text-white'
              }`}
              title={item.name}
            >
              <item.icon className={`w-5 h-5 lg:w-4 lg:h-4 ${isActive ? 'text-black' : 'text-zinc-600'}`} />
              <span className="hidden lg:block">{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-2 lg:p-4 border-t border-zinc-900 shrink-0 space-y-1">
        <Link
          href="/settings"
          className="flex items-center justify-center lg:justify-start gap-3 p-3 lg:px-4 lg:py-3 rounded-2xl text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:bg-zinc-900 hover:text-white transition-all"
          title="Settings"
        >
          <Settings className="w-5 h-5 lg:w-4 lg:h-4 text-zinc-600" />
          <span className="hidden lg:block">Settings</span>
        </Link>
        <button
          onClick={handleLogout}
          className="w-full flex items-center justify-center lg:justify-start gap-3 p-3 lg:px-4 lg:py-3 rounded-2xl text-[10px] font-bold uppercase tracking-widest text-zinc-600 hover:text-red-500 transition-all"
          title="Logout"
        >
          <LogOut className="w-5 h-5 lg:w-4 lg:h-4" />
          <span className="hidden lg:block">Logout</span>
        </button>
      </div>
    </aside>
  );
}
