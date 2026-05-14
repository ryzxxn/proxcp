'use client';

import React, { useEffect, useState } from 'react';
import { 
  Activity, 
  Zap, 
  ShieldCheck, 
  ArrowUpRight,
  ChevronRight,
  Server,
  Wrench,
  Key,
  Loader2,
  X,
  Terminal,
  Code,
  Clock,
  Box,
  BarChart3
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  AreaChart,
  Area
} from 'recharts';
import Link from 'next/link';
import { useSession } from '@/lib/auth-client';
import { api } from '@/lib/api';

export default function Dashboard() {
  const { data: session } = useSession();
  const [stats, setStats] = useState({
    servers: '0',
    tools: '0',
    apiKeys: '0',
    requests: '0'
  });
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState<any | null>(null);

  useEffect(() => {
    if (session?.user?.id) {
      const fetchData = async () => {
        try {
          const [servers, tools, apiKeys, txGroup] = await Promise.all([
            api.getServers(session.user.id),
            api.getTools(session.user.id),
            api.getApiKeys(session.user.id),
            api.getTransactions(session.user.id)
          ]);

          // Flatten and sort transactions by timestamp DESC
          const allTx = Object.values(txGroup)
            .flatMap((g: any) => g.transactions)
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
            .slice(0, 10);
          
          setStats({
            servers: servers.length.toString(),
            tools: tools.length.toString(),
            apiKeys: apiKeys.length.toString(),
            requests: Object.values(txGroup).reduce((acc: number, g: any) => acc + g.transactions.length, 0).toString()
          });
          setTransactions(allTx);
        } catch (error) {
          console.error('Failed to fetch dashboard data:', error);
        } finally {
          setLoading(false);
        }
      };
      fetchData();
    }
  }, [session]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8 md:space-y-12 lg:space-y-16 animate-fade-in text-white bg-black max-w-7xl">
      {/* Welcome Section */}
      <div className="flex items-center justify-between px-2">
        <div>
          <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight uppercase italic">Dashboard</h1>
          <p className="text-zinc-500 mt-1 text-xs md:text-sm font-medium uppercase tracking-widest">System operational status: Optimal</p>
        </div>
        <div className="flex items-center gap-2 bg-zinc-900 text-zinc-400 px-4 py-2 rounded-full text-xs font-bold border border-zinc-800 uppercase tracking-widest">
          <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></div>
          Online
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5">
        {[
          { label: 'Network Nodes', value: stats.servers, icon: Server },
          { label: 'Active Tools', value: stats.tools, icon: Wrench },
          { label: 'Access Control', value: stats.apiKeys, icon: Key },
          { label: 'Data Requests', value: stats.requests, icon: Zap },
        ].map((stat, i) => (
          <div key={i} className="bg-zinc-950 p-4 md:p-5 rounded-2xl border border-zinc-900 shadow-sm hover:border-zinc-700 transition-all group">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 bg-zinc-900 text-zinc-500 group-hover:bg-white group-hover:text-black transition-all`}>
              <stat.icon className="w-4 h-4" />
            </div>
            <div className="text-[7px] md:text-[8px] font-bold text-zinc-600 uppercase tracking-widest">{stat.label}</div>
            <div className="text-xl md:text-2xl font-bold text-white mt-1 italic">{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Latency Graph */}
      <div className="bg-zinc-950 p-6 md:p-8 rounded-[24px] border border-zinc-900">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-lg md:text-xl font-bold uppercase tracking-tight italic flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-zinc-500" />
              Transaction Latency
            </h2>
            <p className="text-zinc-500 text-[10px] uppercase tracking-widest font-bold mt-1">Real-time performance metrics (ms)</p>
          </div>
        </div>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={transactions.slice().reverse().map(tx => ({
                name: tx.tool_name || tx.jsonrpc_method,
                latency: (tx.latency_seconds || 0) * 1000,
                time: new Date(tx.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
              }))}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
            >
              <defs>
                <linearGradient id="colorLatency" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ffffff" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#ffffff" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#18181b" vertical={false} />
              <XAxis 
                dataKey="time" 
                stroke="#52525b" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
                minTickGap={30}
              />
              <YAxis 
                stroke="#52525b" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
                tickFormatter={(value) => `${value}ms`}
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px' }}
                itemStyle={{ color: '#ffffff', fontSize: '12px' }}
                labelStyle={{ color: '#71717a', fontSize: '10px', marginBottom: '4px' }}
              />
              <Area 
                type="monotone" 
                dataKey="latency" 
                stroke="#ffffff" 
                strokeWidth={2}
                fillOpacity={1} 
                fill="url(#colorLatency)" 
                animationDuration={1500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-10">
        {/* Recent Activity */}
        <div className="lg:col-span-3 space-y-6">
          <div className="flex items-center justify-between px-2">
            <h2 className="text-2xl font-bold tracking-tighter uppercase italic">Recent Transactions</h2>
            <Link href="/transactions" className="text-[10px] font-bold text-zinc-600 hover:text-white transition-colors flex items-center gap-2 uppercase tracking-widest">
              Full Log <ArrowUpRight className="w-4 h-4" />
            </Link>
          </div>
          
          <div className="bg-zinc-950 border border-zinc-900 rounded-[32px] overflow-hidden shadow-2xl">
            <div className="divide-y divide-zinc-900">
              {transactions.length > 0 ? transactions.map((tx, i) => (
                <div 
                  key={tx.id || i} 
                  onClick={() => setSelectedTx(tx)}
                  className="p-6 flex items-center justify-between hover:bg-zinc-900/50 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-5">
                    <div className="w-10 h-10 bg-zinc-900 rounded-2xl flex items-center justify-center text-zinc-600 group-hover:bg-white group-hover:text-black transition-all">
                      <Activity className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="text-sm font-bold text-zinc-300 uppercase tracking-tight">{tx.jsonrpc_method}</div>
                      <div className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mt-1">
                        {tx.server_name} • {tx.tool_name || 'Generic'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-8">
                    <div className="text-right">
                       <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{tx.latency_seconds ? `${(tx.latency_seconds * 1000).toFixed(0)}MS` : '---'}</div>
                       <div className={`text-[8px] font-black tracking-widest mt-1 ${(tx.status === 'success' || tx.status === 'accepted') ? 'text-zinc-700' : 'text-red-900'}`}>
                          {tx.status.toUpperCase()}
                       </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-zinc-800 group-hover:text-white transition-all" />
                  </div>
                </div>
              )) : (
                <div className="p-20 text-center text-zinc-800 text-[10px] font-bold uppercase tracking-[0.4em]">No activity detected in sector.</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Transaction Detail Modal */}
      {selectedTx && (
        <div className="fixed inset-0 bg-black/95 backdrop-blur-xl z-50 flex items-center justify-center p-6">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[48px] p-10 max-w-4xl w-full shadow-2xl animate-fade-in flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between mb-8 shrink-0">
              <div className="flex items-center gap-5">
                <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center text-black">
                  <Code className="w-7 h-7" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold tracking-tighter text-white uppercase italic">Transaction Inspector</h2>
                  <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest mt-1">TX_ID: {selectedTx.id}</p>
                </div>
              </div>
              <button 
                onClick={() => setSelectedTx(null)}
                className="p-3 bg-zinc-900 text-zinc-600 hover:text-white rounded-full transition-all"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-6 mb-8 shrink-0">
               <div className="bg-zinc-900/50 p-4 rounded-2xl border border-zinc-800">
                  <div className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Clock className="w-3 h-3" /> Start_Time
                  </div>
                  <div className="text-[11px] font-mono text-zinc-300">
                    {selectedTx.start_timestamp ? new Date(selectedTx.start_timestamp).toLocaleTimeString() : new Date(selectedTx.timestamp).toLocaleTimeString()}
                  </div>
               </div>
               <div className="bg-zinc-900/50 p-4 rounded-2xl border border-zinc-800">
                  <div className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Clock className="w-3 h-3" /> End_Time
                  </div>
                  <div className="text-[11px] font-mono text-zinc-300">
                    {selectedTx.end_timestamp ? new Date(selectedTx.end_timestamp).toLocaleTimeString() : '---'}
                  </div>
               </div>
               <div className="bg-zinc-900/50 p-4 rounded-2xl border border-zinc-800">
                  <div className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Activity className="w-3 h-3" /> Latency
                  </div>
                  <div className="text-[11px] font-mono text-white font-bold">
                    {selectedTx.latency_seconds ? `${(selectedTx.latency_seconds * 1000).toFixed(2)}ms` : '---'}
                  </div>
               </div>
            </div>

            <div className="flex-1 overflow-hidden grid grid-cols-2 gap-8 min-h-0">
              {/* Request */}
              <div className="flex flex-col space-y-4">
                <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest flex items-center gap-2">
                   <ArrowUpRight className="w-3 h-3" />
                   Request Arguments
                </h3>
                <div className="flex-1 bg-black border border-zinc-900 rounded-3xl p-6 overflow-y-auto custom-scrollbar shadow-inner">
                  <pre className="text-xs font-mono text-zinc-400 whitespace-pre-wrap leading-relaxed">
                    {JSON.stringify({ params: selectedTx.request_params?.arguments || selectedTx.request_params }, null, 2)}
                  </pre>
                </div>
              </div>

              {/* Response */}
              <div className="flex flex-col space-y-4">
                <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest flex items-center gap-2">
                   <ChevronRight className="w-3 h-3" />
                   Result Data
                </h3>
                <div className="flex-1 bg-black border border-zinc-900 rounded-3xl p-6 overflow-y-auto custom-scrollbar">
                  <pre className="text-xs font-mono text-zinc-200 whitespace-pre-wrap leading-relaxed">
                    {JSON.stringify(selectedTx.response_data, null, 2)}
                  </pre>
                </div>
              </div>
            </div>

            {/* Raw Data Toggle or Section */}
            <div className="mt-8 pt-8 border-t border-zinc-900">
               <details className="group">
                  <summary className="text-[10px] font-bold text-zinc-700 uppercase tracking-[0.3em] cursor-pointer hover:text-zinc-500 list-none flex items-center gap-2">
                     <Box className="w-3 h-3 group-open:rotate-90 transition-transform" />
                     RAW_TRANSACTION_OBJECT_DUMP
                  </summary>
                  <div className="mt-6 bg-black/40 border border-zinc-900 rounded-2xl p-6 max-h-48 overflow-y-auto custom-scrollbar">
                    <pre className="text-[10px] font-mono text-zinc-600 whitespace-pre-wrap">
                      {JSON.stringify(selectedTx, null, 2)}
                    </pre>
                  </div>
               </details>
            </div>

            <div className="mt-8 pt-8 border-t border-zinc-900 flex justify-between items-center shrink-0">
              <div className="flex gap-8">
                 <div className="space-y-1">
                    <span className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest block">Execution Time</span>
                    <span className="text-sm font-bold text-zinc-400 italic">
                       {selectedTx.latency_seconds ? `${(selectedTx.latency_seconds * 1000).toFixed(2)}ms` : 'N/A'}
                    </span>
                 </div>
                 <div className="space-y-1">
                    <span className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest block">Timestamp</span>
                    <span className="text-sm font-bold text-zinc-400 italic">
                       {new Date(selectedTx.timestamp).toLocaleString()}
                    </span>
                 </div>
                 <div className="space-y-1">
                    <span className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest block">Node</span>
                    <span className="text-sm font-bold text-zinc-400 italic uppercase tracking-tighter">
                       {selectedTx.server_name}
                    </span>
                 </div>
              </div>
              <button 
                onClick={() => setSelectedTx(null)}
                className="px-10 py-4 bg-white text-black font-black uppercase tracking-[0.3em] text-xs rounded-2xl hover:bg-zinc-200 transition-all shadow-xl italic"
              >
                Close_Session
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
