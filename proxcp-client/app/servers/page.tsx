'use client';

import React, { useEffect, useState } from 'react';
import { Server, Plus, Shield, Globe, Activity, Loader2, Trash2, RefreshCw, X } from 'lucide-react';
import { useSession } from '@/lib/auth-client';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function ServersPage() {
  const { data: session } = useSession();
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newServer, setNewServer] = useState({ name: '', url: '', token: '' });

  const fetchServers = async () => {
    if (session?.user?.id) {
      try {
        const data = await api.getServers(session.user.id);
        setServers(data);
      } catch (error) {
        console.error('Failed to fetch servers:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchServers();
  }, [session]);

  const handleAddServer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session?.user?.id) return;
    try {
      await api.addServer(session.user.id, newServer);
      setNewServer({ name: '', url: '', token: '' });
      setShowAddModal(false);
      await fetchServers();
      // Trigger a full sync after adding a new server to ensure tools are populated
      handleSync();
      toast.success('Server added successfully');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleDeleteServer = async (serverId: string) => {
    if (!session?.user?.id || !confirm('Confirm deletion of network node?')) return;
    try {
      await api.deleteServer(session.user.id, serverId);
      fetchServers();
      toast.success('Node deleted');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleSync = async () => {
    if (!session?.user?.id) return;
    setIsSyncing(true);
    try {
      const response = await api.syncServers(session.user.id);
      const results = response.results || {};
      const urls = Object.keys(results);
      const errors = urls.filter(url => results[url].status === 'error');
      
      if (errors.length > 0) {
        toast.error(`Sync completed with errors for ${errors.length} nodes: ${errors.join(', ')}`);
      } else {
        toast.success(`Sync successful. Discovered ${urls.reduce((acc, url) => acc + (results[url].tools?.length || 0), 0)} tools across ${urls.length} nodes.`);
      }
    } catch (error) {
      toast.error('Sync failed: ' + (error as any).message);
    } finally {
      setIsSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 md:space-y-8 lg:space-y-10 animate-fade-in text-white bg-black w-full">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 px-2">
        <div>
          <h1 className="text-2xl md:text-3xl lg:text-4xl font-bold tracking-tight uppercase italic">Network Nodes</h1>
          <p className="text-zinc-500 text-[10px] md:text-xs font-medium mt-0.5 uppercase tracking-widest italic">Manage and monitor connected MCP nodes</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button 
            onClick={handleSync}
            disabled={isSyncing}
            className="flex-1 md:flex-none flex items-center justify-center gap-2.5 bg-zinc-900 border border-zinc-800 text-zinc-400 px-5 py-3 rounded-xl text-[9px] font-bold uppercase tracking-widest hover:bg-zinc-800 transition-all disabled:opacity-50 italic"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
            Sync Library
          </button>
          <button 
            onClick={() => setShowAddModal(true)}
            className="flex-1 md:flex-none flex items-center justify-center gap-2.5 bg-white text-black px-5 py-3 rounded-xl text-[9px] font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all italic shadow-2xl shadow-white/5"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Node
          </button>
        </div>
      </div>

      <div className="grid gap-5 md:gap-6 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        {servers.map((server) => (
          <div key={server.id} className="bg-zinc-950 border border-zinc-900 rounded-[20px] md:rounded-[24px] p-5 md:p-6 lg:p-7 hover:border-zinc-700 transition-all group relative overflow-hidden shadow-sm hover:shadow-xl">
            <div className="flex items-start justify-between mb-6 relative z-10">
              <div className={`w-10 h-10 md:w-12 md:h-12 rounded-xl border border-zinc-800 flex items-center justify-center ${server.is_active ? 'bg-white text-black' : 'text-zinc-700'} transition-all`}>
                <Server className="w-5 h-5 md:w-6 md:h-6" />
              </div>
              <button 
                onClick={() => handleDeleteServer(server.id)}
                className="p-2 text-zinc-800 hover:text-red-500 transition-colors"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
            
            <div className="relative z-10">
              <h3 className="text-xl font-bold text-white tracking-tight">{server.name || 'Unnamed Node'}</h3>
              <div className="flex items-center gap-2 text-zinc-500 text-xs font-medium mt-2 truncate">
                <Globe className="w-3.5 h-3.5 shrink-0" />
                {server.url}
              </div>
            </div>

            <div className="flex items-center justify-between mt-10 pt-6 border-t border-zinc-900 relative z-10">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${server.is_active ? 'bg-white animate-pulse' : 'bg-zinc-800'}`}></div>
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                  {server.is_active ? 'Online' : 'Offline'}
                </span>
              </div>
              <div className="flex items-center gap-4 text-zinc-800">
                <Shield className="w-3.5 h-3.5" />
                <Activity className="w-3.5 h-3.5" />
              </div>
            </div>
          </div>
        ))}

        <button 
          onClick={() => setShowAddModal(true)}
          className="border-2 border-dashed border-zinc-900 rounded-3xl p-8 flex flex-col items-center justify-center text-zinc-700 hover:text-zinc-500 hover:border-zinc-700 hover:bg-zinc-950/50 transition-all group min-h-[260px]"
        >
          <div className="w-16 h-16 rounded-full bg-zinc-900 flex items-center justify-center mb-6 group-hover:bg-zinc-800 transition-all">
            <Plus className="w-8 h-8 stroke-[1.5]" />
          </div>
          <span className="text-xs font-bold uppercase tracking-widest">Connect New Node</span>
        </button>
      </div>

      {/* Add Server Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-md z-50 flex items-center justify-center p-6">
          <div className="bg-zinc-950 border border-zinc-900 rounded-3xl p-10 max-w-md w-full animate-fade-in-up shadow-2xl">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-2xl font-bold text-white tracking-tight">Connect Node</h2>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-700 hover:text-white transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            
            <form onSubmit={handleAddServer} className="space-y-8">
              <div className="space-y-3">
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Label Tag</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g. Production Cluster"
                  className="w-full bg-black border border-zinc-900 rounded-2xl px-5 py-4 text-sm font-medium text-white outline-none focus:border-white transition-all placeholder:text-zinc-800"
                  value={newServer.name}
                  onChange={e => setNewServer({...newServer, name: e.target.value})}
                />
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Endpoint URL</label>
                <input 
                  type="url" 
                  required
                  placeholder="https://node.example.com"
                  className="w-full bg-black border border-zinc-900 rounded-2xl px-5 py-4 text-sm font-medium text-white outline-none focus:border-white transition-all placeholder:text-zinc-800"
                  value={newServer.url}
                  onChange={e => setNewServer({...newServer, url: e.target.value})}
                />
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Security Token</label>
                <input 
                  type="password" 
                  placeholder="••••••••••••"
                  className="w-full bg-black border border-zinc-900 rounded-2xl px-5 py-4 text-sm font-medium text-white outline-none focus:border-white transition-all placeholder:text-zinc-800"
                  value={newServer.token}
                  onChange={e => setNewServer({...newServer, token: e.target.value})}
                />
              </div>
              
              <button 
                type="submit"
                className="w-full py-5 bg-white text-black font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all rounded-2xl shadow-lg"
              >
                Link Protocol
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
