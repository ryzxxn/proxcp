'use client';

import React from 'react';
import Sidebar from './Sidebar';
import { useSession } from '@/lib/auth-client';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { data: session, isPending } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (!isPending && !session && pathname !== '/login') {
      router.push('/login');
    }
  }, [session, isPending, router, pathname]);

  if (isPending) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="w-8 h-8 text-slate-900 animate-spin" />
      </div>
    );
  }

  if (!session && pathname !== '/login') {
    return null;
  }

  if (pathname === '/login') {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen bg-black overflow-hidden transition-colors duration-300">
      <Sidebar />
      <main className="flex-1 overflow-y-auto flex flex-col p-4 md:p-6 lg:p-8 bg-black">
        <div className="w-full max-w-[1600px] h-full flex flex-col">
          {children}
        </div>
      </main>
    </div>
  );
}
