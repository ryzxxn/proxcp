'use client';

import React, { useEffect, useState } from 'react';
import { Key, Plus, Copy, Trash2, Eye, Calendar, Clock, Loader2, Check, Wrench, X, ChevronRight, Activity, Minus, Box, Search, Filter } from 'lucide-react';
import { useSession } from '@/lib/auth-client';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function AccessControlPage() {
  const { data: session } = useSession();
  const [keys, setKeys] = useState<any[]>([]);
  const [allTools, setAllTools] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showKeyModal, setShowKeyModal] = useState<any | null>(null);
  const [newKeyName, setNewKeyName] = useState('');
  
  // Mapping State
  const [selectedKey, setSelectedKey] = useState<any | null>(null);
  const [keyTools, setKeyTools] = useState<any[]>([]);
  const [loadingMappings, setLoadingMappings] = useState(false);
  
  // Mapping Filters
  const [toolSearch, setToolConfigSearch] = useState('');
  const [serverFilter, setServerFilter] = useState<string>('ALL');

  const fetchKeys = async () => {
    if (session?.user?.id) {
      try {
        const [keysData, toolsData] = await Promise.all([
          api.getApiKeys(session.user.id),
          api.getTools(session.user.id)
        ]);
        setKeys(keysData);
        setAllTools(toolsData);
      } catch (error) {
        console.error('Failed to fetch data:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchKeys();
  }, [session]);

  const fetchMappings = async (toolConfigId: string) => {
    if (!session?.user?.id) return;
    setLoadingMappings(true);
    try {
      const data = await api.getApiKeyTools(session.user.id, toolConfigId);
      setKeyTools(data);
    } catch (error) {
      console.error('Failed to fetch mappings:', error);
    } finally {
      setLoadingMappings(false);
    }
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session?.user?.id || !newKeyName) return;
    setIsCreating(true);
    try {
      const data = await api.createApiKey(session.user.id, newKeyName);
      setNewKeyName('');
      setShowKeyModal(data);
      fetchKeys();
      toast.success('Access key generated');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteKey = async (keyId: string) => {
    if (!session?.user?.id || !confirm('Confirm deletion of access key?')) return;
    try {
      await api.deleteApiKey(session.user.id, keyId);
      fetchKeys();
      toast.success('Access key deleted');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleAddTool = async (toolId: string) => {
    if (!session?.user?.id || !selectedKey) return;
    try {
      await api.addToolToApiKey(session.user.id, selectedKey.tool_config_id, toolId);
      fetchMappings(selectedKey.tool_config_id);
      toast.success('Tool attached');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleRemoveTool = async (mappingId: string) => {
    if (!session?.user?.id || !selectedKey) return;
    try {
      await api.removeToolFromApiKey(session.user.id, selectedKey.tool_config_id, mappingId);
      fetchMappings(selectedKey.tool_config_id);
      toast.success('Tool removed');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleSyncAll = async () => {
    if (!session?.user?.id || !selectedKey) return;
    try {
      await api.syncAllToolsToApiKey(session.user.id, selectedKey.tool_config_id);
      fetchMappings(selectedKey.tool_config_id);
      toast.success('All tools synced to key');
    } catch (error) {
      toast.error('Error: ' + (error as any).message);
    }
  };

  const handleAddFiltered = async (filteredTools: any[]) => {
    if (!session?.user?.id || !selectedKey || filteredTools.length === 0) return;
    try {
      setLoadingMappings(true);
      // Sequentially add each tool (backend could be optimized for bulk, but this is safer for now)
      for (const tool of filteredTools) {
        await api.addToolToApiKey(session.user.id, selectedKey.tool_config_id, tool.id);
      }
      fetchMappings(selectedKey.tool_config_id);
      toast.success(`Attached ${filteredTools.length} tools`);
    } catch (error) {
      toast.error('Batch add failed: ' + (error as any).message);
    } finally {
      setLoadingMappings(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(text);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    );
  }

  // Get unique servers from allTools
  const uniqueServers = Array.from(new Set(allTools.map(t => t.server_name || t.server_url || 'Unknown'))).sort();

  // Available tools logic
  const availableTools = allTools
    .filter(t => !keyTools.some(m => m.tool_id === t.id))
    .filter(t => {
      const matchesSearch = t.name.toLowerCase().includes(toolSearch.toLowerCase());
      const serverName = t.server_name || t.server_url || 'Unknown';
      const matchesServer = serverFilter === 'ALL' || serverName === serverFilter;
      return matchesSearch && matchesServer;
    });

  return (
    <div className="space-y-6 md:space-y-8 lg:space-y-10 animate-fade-in text-white bg-black w-full">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 px-2">
        <div>
          <h1 className="text-2xl md:text-3xl lg:text-4xl font-bold tracking-tight uppercase italic">Access Control</h1>
          <p className="text-zinc-500 text-[10px] md:text-xs font-medium mt-0.5 uppercase tracking-widest italic">Manage external connection tokens</p>
        </div>
        <form onSubmit={handleCreateKey} className="flex flex-col sm:flex-row gap-3">
          <input 
            type="text" 
            placeholder="Label_Tag_..." 
            className="bg-zinc-950 border border-zinc-900 rounded-xl px-5 py-3 text-sm font-bold text-white outline-none focus:border-white transition-all placeholder:text-zinc-800 uppercase italic"
            value={newKeyName}
            onChange={e => setNewKeyName(e.target.value)}
            required
          />
          <button 
            type="submit"
            disabled={isCreating}
            className="flex items-center justify-center gap-2.5 bg-white text-black px-6 py-3 rounded-xl text-[9px] font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all disabled:opacity-50 shadow-2xl shadow-white/5 italic"
          >
            {isCreating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Generate_Key
          </button>
        </form>
      </div>

      <div className="space-y-5 md:space-y-6">
        {keys.length > 0 ? keys.map((key) => (
          <div key={key.id} className="bg-zinc-950 border border-zinc-900 rounded-[20px] md:rounded-[24px] p-5 md:p-6 lg:p-7 hover:border-zinc-700 transition-all group shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
              <div className="flex gap-5 md:gap-6">
                <div className="w-10 h-10 md:w-12 md:h-12 rounded-xl border border-zinc-800 flex items-center justify-center text-white bg-zinc-900/50 shrink-0">
                  <Key className="w-5 h-5 md:w-6 md:h-6" />
                </div>
                <div>
                  <h3 className="text-lg md:text-xl font-bold tracking-tight uppercase italic">{key.name}</h3>
                  <div className="flex items-center gap-5 mt-2">
                    <div className="flex items-center gap-2 text-[9px] text-zinc-500 font-bold uppercase tracking-widest">
                      <Calendar className="w-3 h-3 text-zinc-700" />
                      Issued: {new Date(key.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <button 
                  onClick={() => {
                    setSelectedKey(key);
                    fetchMappings(key.tool_config_id);
                  }}
                  className="flex-1 lg:flex-none flex items-center justify-center gap-2.5 px-5 py-3 bg-zinc-900 text-zinc-300 rounded-xl text-[9px] font-bold uppercase tracking-widest hover:bg-white hover:text-black transition-all italic border border-zinc-800"
                >
                  <Wrench className="w-3.5 h-3.5" />
                  Configure_Tools
                </button>
                <button 
                  onClick={() => copyToClipboard(key.key)}
                  className="p-3 bg-zinc-900 text-zinc-600 hover:text-white rounded-lg transition-all border border-zinc-800"
                  title="Copy Key"
                >
                  {copiedKey === key.key ? <Check className="w-4 h-4 text-white" /> : <Copy className="w-4 h-4" />}
                </button>
                <button 
                  onClick={() => handleDeleteKey(key.id)}
                  className="p-3 bg-zinc-900 text-zinc-800 hover:text-red-500 rounded-lg transition-all border border-zinc-800"
                  title="Revoke Key"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="mt-6 md:mt-8 flex flex-col md:flex-row items-stretch md:items-center gap-3">
              <code className="bg-black border border-zinc-900 px-5 py-3 rounded-lg text-[10px] md:text-xs font-mono text-zinc-600 flex-1 truncate tracking-wider shadow-inner">
                {key.key.substring(0, 32)}••••••••••••••••••••••••••••••••
              </code>
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest bg-zinc-900 px-5 py-3 border border-zinc-800 rounded-lg text-center italic">
                PROTOCOL_ACTIVE
              </span>
            </div>
          </div>
        )) : (
          <div className="p-24 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-[32px]">
            <div className="text-3xl font-bold mb-4 opacity-10">No Access Records</div>
            <p className="text-xs font-medium uppercase tracking-widest">Initialize security protocol to generate access control tokens.</p>
          </div>
        )}
      </div>

      {/* Tools Mapping Modal */}
      {selectedKey && (
        <div className="fixed inset-0 bg-black/95 backdrop-blur-xl z-50 flex items-center justify-center p-4 lg:p-8">
          <div className="w-full max-w-7xl bg-zinc-950 border border-zinc-900 rounded-[48px] shadow-2xl animate-fade-in flex flex-col h-[90vh] overflow-hidden">
            <div className="p-10 border-b border-zinc-900 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-6">
                <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center text-black shadow-lg">
                  <Wrench className="w-7 h-7" />
                </div>
                <div>
                  <h2 className="text-3xl font-bold tracking-tighter text-white">Permissions Matrix</h2>
                  <p className="text-xs text-zinc-500 font-bold mt-1 uppercase tracking-widest italic">KEY_TARGET::{selectedKey.name}</p>
                </div>
              </div>
              <button 
                onClick={() => {
                  setSelectedKey(null);
                  setToolConfigSearch('');
                  setServerFilter('ALL');
                }}
                className="p-4 bg-zinc-900 text-zinc-500 hover:text-white rounded-full transition-all"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <div className="flex-1 overflow-hidden grid grid-cols-2 min-h-0">
              {/* Available Library (Left) */}
              <div className="flex flex-col border-r border-zinc-900 p-10 space-y-8 min-h-0">
                <div className="space-y-6 shrink-0">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-[0.2em]">Available Library</h3>
                    {(toolSearch || serverFilter !== 'ALL') && availableTools.length > 0 && (
                      <button 
                        onClick={() => handleAddFiltered(availableTools)}
                        className="text-[10px] font-black text-white bg-zinc-900 px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition-all uppercase tracking-widest flex items-center gap-2"
                      >
                        <Plus className="w-3 h-3" />
                        Attach {availableTools.length} Result{availableTools.length !== 1 ? 's' : ''}
                      </button>
                    )}
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-700" />
                      <input 
                        type="text" 
                        placeholder="Search tools..." 
                        value={toolSearch}
                        onChange={e => setToolConfigSearch(e.target.value)}
                        className="w-full bg-black border border-zinc-900 rounded-xl pl-10 pr-4 py-3 text-xs font-medium text-white outline-none focus:border-zinc-500 transition-all placeholder:text-zinc-800"
                      />
                    </div>
                    <div className="relative">
                      <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-700" />
                      <select 
                        value={serverFilter}
                        onChange={e => setServerFilter(e.target.value)}
                        className="w-full bg-black border border-zinc-900 rounded-xl pl-10 pr-4 py-3 text-xs font-medium text-white outline-none focus:border-zinc-500 transition-all appearance-none cursor-pointer"
                      >
                        <option value="ALL">All Nodes</option>
                        {uniqueServers.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                  {availableTools.length > 0 ? (
                    availableTools.map((tool) => (
                      <div key={tool.id} className="flex items-center justify-between p-5 bg-zinc-900/20 border border-zinc-900 rounded-3xl group hover:border-zinc-600 transition-all shrink-0">
                        <div className="flex items-center gap-5">
                          <div className="w-10 h-10 rounded-2xl bg-zinc-900 flex items-center justify-center text-zinc-700 group-hover:text-zinc-400 transition-all">
                            <Box className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="text-sm font-bold text-zinc-400 group-hover:text-white transition-colors">{tool.name}</div>
                            <div className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest mt-1 italic">{tool.server_name || tool.server_url}</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => handleAddTool(tool.id)}
                          className="p-3 bg-zinc-900 text-zinc-600 hover:text-white rounded-2xl transition-all"
                          title="Attach Tool"
                        >
                          <Plus className="w-5 h-5" />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="h-full flex items-center justify-center text-center text-zinc-800 text-[10px] font-bold uppercase border-2 border-dashed border-zinc-900 rounded-[32px] p-12 tracking-[0.4em]">
                      {allTools.length === keyTools.length ? 'Library Fully Linked' : 'No matches found'}
                    </div>
                  )}
                </div>
              </div>

              {/* Attached Tools (Right) */}
              <div className="flex flex-col p-10 space-y-8 min-h-0 bg-zinc-950">
                <div className="flex items-center justify-between shrink-0">
                  <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-[0.2em]">Attached Access</h3>
                  <button 
                    onClick={handleSyncAll}
                    className="text-[10px] font-black text-zinc-500 flex items-center gap-3 hover:text-white transition-colors uppercase tracking-widest"
                  >
                    <Activity className="w-4 h-4" />
                    Reset & Sync All
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                  {loadingMappings ? (
                    <div className="flex justify-center p-12">
                      <Loader2 className="w-10 h-10 animate-spin text-zinc-800" />
                    </div>
                  ) : keyTools.length > 0 ? (
                    keyTools.map((mapping) => (
                      <div key={mapping.id} className="flex items-center justify-between p-5 bg-black border border-zinc-900 rounded-3xl group hover:border-zinc-700 transition-all shrink-0">
                        <div className="flex items-center gap-5">
                          <div className="w-2 h-2 rounded-full bg-white opacity-20 group-hover:opacity-100 transition-all shadow-glow"></div>
                          <div>
                            <div className="text-sm font-bold uppercase tracking-tight text-zinc-200">{mapping.tool_name}</div>
                            <div className="text-[10px] text-zinc-600 font-bold mt-1 italic uppercase tracking-widest">{mapping.server_name}</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => handleRemoveTool(mapping.id)}
                          className="p-3 bg-zinc-900 text-zinc-700 hover:text-red-500 rounded-2xl transition-all"
                          title="Remove Tool"
                        >
                          <Minus className="w-5 h-5" />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="h-full flex items-center justify-center text-center text-zinc-800 text-[10px] font-bold uppercase border-2 border-dashed border-zinc-900 rounded-[32px] p-12 tracking-[0.4em]">
                      Access Restricted
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            <div className="p-10 border-t border-zinc-900 flex justify-between items-center shrink-0">
               <div className="text-[10px] font-bold text-zinc-700 uppercase tracking-widest italic">
                  Link count: {keyTools.length} total modules attached
               </div>
               <button 
                onClick={() => setSelectedKey(null)}
                className="px-12 py-4 bg-white text-black font-black uppercase tracking-[0.3em] text-xs rounded-2xl hover:bg-zinc-200 transition-all shadow-xl"
              >
                Protocol Confirmed
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Key Modal */}
      {showKeyModal && (
        <div className="fixed inset-0 bg-black/95 backdrop-blur-xl z-50 flex items-center justify-center p-6">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[40px] p-12 max-w-xl w-full shadow-2xl animate-fade-in-up text-center shadow-white/5">
            <h2 className="text-3xl font-bold text-white tracking-tight mb-4 uppercase italic">Token Generated</h2>
            <p className="text-zinc-500 text-sm font-medium mb-10 leading-relaxed px-8">Copy the identification string below. For system integrity, this token will not be displayed again.</p>
            
            <div className="space-y-8">
              <div className="relative group">
                <textarea 
                  readOnly 
                  rows={4}
                  className="w-full bg-black border border-zinc-900 rounded-3xl p-8 font-mono text-sm text-zinc-300 outline-none leading-relaxed tracking-wider shadow-inner"
                  value={showKeyModal.key}
                />
                <button 
                  onClick={() => copyToClipboard(showKeyModal.key)}
                  className="absolute right-4 bottom-4 p-4 bg-white text-black hover:bg-zinc-200 transition-all shadow-xl rounded-2xl"
                >
                  {copiedKey === showKeyModal.key ? <Check className="w-5 h-5 text-black" /> : <Copy className="w-5 h-5" />}
                </button>
              </div>
              
              <button 
                onClick={() => setShowKeyModal(null)}
                className="w-full py-6 bg-white text-black font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all text-xs rounded-2xl shadow-lg"
              >
                Protocol Confirmed
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
