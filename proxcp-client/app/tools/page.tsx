'use client';

import React, { useEffect, useState } from 'react';
import { Wrench, Search, Play, Box, Loader2, X, Terminal, ChevronRight, Info, AlertCircle, ChevronLeft, ArrowRight, Activity, Clock, ArrowUpRight } from 'lucide-react';
import { useSession } from '@/lib/auth-client';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function ToolsPage() {
  const { data: session } = useSession();
  const [tools, setTools] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  
  // View State
  const [selectedTool, setSelectedTool] = useState<any | null>(null);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<any | null>(null);
  const [formInputs, setFormInputs] = useState<Record<string, any>>({});

  useEffect(() => {
    if (session?.user?.id) {
      const fetchTools = async () => {
        try {
          const data = await api.getTools(session.user.id);
          setTools(data);
        } catch (error) {
          console.error('Failed to fetch tools:', error);
        } finally {
          setLoading(false);
        }
      };
      fetchTools();
    }
  }, [session]);

  const selectTool = (tool: any) => {
    setSelectedTool(tool);
    setExecResult(null);
    
    // Initialize form inputs based on tool schema
    const definition = tool.definition ? JSON.parse(tool.definition) : {};
    const properties = definition.inputSchema?.properties || {};
    const initialInputs: Record<string, any> = {};
    Object.keys(properties).forEach(key => {
      initialInputs[key] = properties[key].default || "";
    });
    setFormInputs(initialInputs);
  };

  const handleExecute = async () => {
    if (!session?.user?.id || !selectedTool) return;
    setExecuting(true);
    setExecResult(null);
    try {
      const result = await api.executeTool({
        user_id: session.user.id,
        session_id: 'ui-session-' + Date.now(),
        tool_name: selectedTool.name,
        server_url: selectedTool.server_url,
        params: formInputs
      });
      setExecResult(result);
    } catch (error: any) {
      setExecResult({ error: error.message || 'Execution failed' });
    } finally {
      setExecuting(false);
    }
  };

  const filteredTools = tools.filter(tool => 
    tool.name.toLowerCase().includes(search.toLowerCase()) || 
    (tool.server_name || '').toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black h-[80vh]">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    );
  }

  // Grid View (Default)
  if (!selectedTool) {
    return (
      <div className="space-y-6 md:space-y-8 lg:space-y-10 animate-fade-in text-white bg-black w-full">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 px-2">
          <div>
            <h1 className="text-2xl md:text-3xl lg:text-4xl font-bold tracking-tight text-white uppercase italic">Tools Library</h1>
            <p className="text-zinc-500 text-[10px] md:text-xs font-medium mt-0.5 uppercase tracking-widest">Explore and test your connected capabilities</p>
          </div>
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input 
              type="text" 
              placeholder="FILTER_LIBRARY_..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-2xl pl-12 pr-4 py-3 md:py-4 text-xs md:text-sm font-bold text-white outline-none focus:border-zinc-500 transition-all placeholder:text-zinc-700 w-full md:w-80 uppercase italic"
            />
          </div>
        </div>

        {filteredTools.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 md:gap-6">
            {filteredTools.map((tool) => {
              const definition = tool.definition ? JSON.parse(tool.definition) : {};
              return (
                <button
                  key={tool.id}
                  onClick={() => selectTool(tool)}
                  className="bg-zinc-950 border border-zinc-900 rounded-[20px] md:rounded-[24px] p-5 md:p-6 hover:border-zinc-600 transition-all group text-left relative overflow-hidden flex flex-col h-full shadow-sm hover:shadow-xl"
                >
                  <div className="flex items-center justify-between mb-6">
                    <div className="w-10 h-10 md:w-12 md:h-12 rounded-xl border border-zinc-800 flex items-center justify-center text-zinc-600 group-hover:text-white transition-all">
                      <Box className="w-5 h-5 md:w-6 md:h-6" />
                    </div>
                    <ArrowRight className="w-4 h-4 text-zinc-800 group-hover:text-white transition-all -translate-x-2 opacity-0 group-hover:opacity-100 group-hover:translate-x-0" />
                  </div>
                  
                  <div className="flex-1">
                    <h3 className="text-base md:text-lg font-bold text-white mb-2 uppercase tracking-tight italic">{tool.name}</h3>
                    <p className="text-zinc-500 text-[10px] md:text-xs font-medium leading-relaxed line-clamp-3 italic">
                      {definition.description || 'System module providing specialized functions.'}
                    </p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-zinc-900 flex items-center justify-between">
                    <span className="text-[8px] md:text-[9px] font-bold text-zinc-600 uppercase tracking-widest">{tool.server_name || 'Generic Node'}</span>
                    <span className="bg-emerald-500/10 text-emerald-500 px-1.5 py-0.5 rounded text-[7px] font-bold uppercase tracking-tighter">Ready</span>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="py-24 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-[32px]">
            <div className="text-3xl font-bold mb-2">No Results</div>
            <p className="text-sm font-medium uppercase tracking-widest">Adjust filters to find tool</p>
          </div>
        )}
      </div>
    );
  }

  // Detail / Testing View
  const definition = selectedTool.definition ? JSON.parse(selectedTool.definition) : {};
  const properties = definition.inputSchema?.properties || {};

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col animate-fade-in bg-black text-white">
      <div className="flex items-center justify-between mb-8 shrink-0">
        <div className="flex items-center gap-6">
          <button 
            onClick={() => setSelectedTool(null)}
            className="w-12 h-12 bg-zinc-950 border border-zinc-900 rounded-2xl flex items-center justify-center text-zinc-500 hover:text-white hover:border-zinc-700 transition-all shadow-sm"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <span className="bg-zinc-900 text-zinc-500 px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest">Path::{selectedTool.name}</span>
            </div>
            <h1 className="text-4xl font-bold tracking-tighter text-white mt-1 uppercase italic">{selectedTool.name}</h1>
          </div>
        </div>
        <div className="flex items-center gap-3 text-zinc-500 bg-zinc-950 border border-zinc-900 px-5 py-2.5 rounded-2xl">
          <Terminal className="w-4 h-4" />
          <span className="text-[10px] font-bold uppercase tracking-widest truncate max-w-[300px]">{selectedTool.server_url}</span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden grid grid-cols-12 gap-8">
        {/* Left Column: Tool Details & Inputs */}
        <div className="col-span-12 lg:col-span-4 flex flex-col space-y-8 overflow-y-auto pr-4 custom-scrollbar min-h-0">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[32px] p-10 space-y-10">
            <div className="space-y-4">
              <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.3em] flex items-center gap-2">
                <Info className="w-3.5 h-3.5" />
                Documentation
              </h3>
              <p className="text-zinc-400 text-lg font-medium leading-relaxed italic">
                {definition.description || 'System module providing specialized functions.'}
              </p>
            </div>

            <div className="pt-10 border-t border-zinc-900 space-y-10">
              <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.3em] flex items-center gap-2">
                <Wrench className="w-3.5 h-3.5" />
                Parameters
              </h3>
              
              <div className="space-y-8">
                {Object.keys(properties).length > 0 ? (
                  Object.entries(properties).map(([key, schema]: [string, any]) => (
                    <div key={key} className="space-y-3">
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest italic">{key}</label>
                        {schema.type && <span className="text-[9px] font-black text-zinc-800 uppercase tracking-widest">Type::{schema.type}</span>}
                      </div>
                      <input 
                        type={schema.type === 'number' ? 'number' : 'text'}
                        placeholder={`_ASSIGN_${key.toUpperCase()}_`}
                        className="w-full bg-black border border-zinc-900 rounded-2xl p-5 text-sm font-bold text-white outline-none focus:border-white transition-all placeholder:text-zinc-900 uppercase"
                        value={formInputs[key]}
                        onChange={(e) => setFormInputs({...formInputs, [key]: schema.type === 'number' ? Number(e.target.value) : e.target.value})}
                      />
                      {schema.description && <p className="text-[9px] text-zinc-700 font-bold uppercase tracking-tight italic opacity-50">{schema.description}</p>}
                    </div>
                  ))
                ) : (
                  <div className="p-12 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-3xl text-[10px] font-bold uppercase tracking-widest">
                    No variables required
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Results & Logs */}
        <div className="col-span-12 lg:col-span-8 flex flex-col space-y-8 h-full overflow-hidden min-h-0">
          <div className="flex-1 bg-zinc-950 border border-zinc-900 rounded-[32px] flex flex-col overflow-hidden shadow-2xl relative">
            <div className="p-8 border-b border-zinc-900 flex items-center justify-between shrink-0 bg-zinc-950/50 backdrop-blur-sm z-10">
              <div className="flex items-center gap-4">
                <button 
                  onClick={handleExecute}
                  disabled={executing}
                  className="px-4 py-2 bg-white text-black text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all flex items-center justify-center gap-2 group disabled:opacity-50 rounded-lg shadow-lg mr-2"
                >
                  {executing ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="w-2.5 h-2.5 fill-black group-hover:scale-110 transition-transform" />
                      Execute Tool
                    </>
                  )}
                </button>

                {execResult?.latency_seconds !== undefined && (
                  <div className="flex items-center gap-2 bg-zinc-900 px-3 py-1.5 rounded-lg border border-zinc-800">
                    <Clock className="w-3 h-3 text-zinc-600" />
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                      {(execResult.latency_seconds * 1000).toFixed(2)}ms
                    </span>
                  </div>
                )}
                <div className={`px-4 py-1.5 rounded-full text-[9px] font-bold uppercase tracking-widest border ${execResult ? (execResult.error ? 'bg-red-500/10 border-red-500/20 text-red-500' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500') : 'bg-zinc-900 border-zinc-800 text-zinc-700'}`}>
                  {execResult ? (execResult.error ? 'Execution_Error' : 'Complete_Success') : 'Idle_State'}
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-10 custom-scrollbar bg-black/40">
              <div className="space-y-10 animate-fade-in">
                  {/* Request Payload Section - Realtime updates */}
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 opacity-50">
                      <ArrowUpRight className="w-3 h-3" />
                      <span className="text-[9px] font-black uppercase tracking-[0.2em]">Request_Payload</span>
                    </div>
                    <div className="bg-black/50 border border-zinc-900 rounded-2xl p-6 shadow-inner">
                      <pre className="text-[11px] font-mono text-zinc-500 whitespace-pre-wrap leading-relaxed">
                        {JSON.stringify({ params: formInputs }, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* Response Data Section */}
                  {execResult ? (
                    <div className="space-y-4">
                      <div className="flex items-center gap-3 opacity-50">
                        <ChevronRight className="w-3 h-3" />
                        <span className="text-[9px] font-black uppercase tracking-[0.2em]">Response_Data</span>
                      </div>
                      <div className="bg-zinc-900/30 border border-zinc-900 rounded-3xl p-8 relative overflow-hidden shadow-2xl">
                        <div className="absolute top-0 right-0 p-3 bg-zinc-900 text-[8px] font-bold text-zinc-600 uppercase tracking-widest italic">BUFFER_0x01</div>
                        <pre className="text-xs font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed selection:bg-white selection:text-black">
                          {JSON.stringify(execResult, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ) : (
                    <div className="pt-12 text-center opacity-10">
                        <div className="text-center space-y-6">
                          <Activity className="w-20 h-20 text-zinc-500 mx-auto stroke-[0.5]" />
                          <div className="text-sm font-bold text-zinc-500 uppercase tracking-[0.8em] italic">Waiting_for_Execute</div>
                        </div>
                    </div>
                  )}
              </div>
            </div>
            
            <div className="p-6 bg-zinc-900/30 border-t border-zinc-900 flex justify-between items-center shrink-0">
              <div className="flex gap-3">
                <div className="w-2 h-2 rounded-full bg-zinc-800"></div>
                <div className="w-2 h-2 rounded-full bg-zinc-800"></div>
                <div className="w-2 h-2 rounded-full bg-zinc-800"></div>
              </div>
              <span className="text-[8px] font-black text-zinc-800 uppercase tracking-[0.4em] italic">Proxcp Virtual Terminal // v1.0.4-Alpha</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
