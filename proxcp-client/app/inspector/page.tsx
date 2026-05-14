'use client';

import React, { useEffect, useState } from 'react';
import { Wrench, Search, Play, Box, Loader2, X, Terminal, ChevronRight, Info, AlertCircle, ChevronLeft, ArrowRight, Activity, Clock, ArrowUpRight } from 'lucide-react';
import { useSession } from '@/lib/auth-client';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function InspectorPage() {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState('Tools');
  const [tools, setTools] = useState<any[]>([]);
  const [resources, setResources] = useState<any[]>([]);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  
  // View State
  const [selectedTool, setSelectedTool] = useState<any | null>(null);
  const [selectedResource, setSelectedResource] = useState<any | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<any | null>(null);
  
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<any | null>(null);
  const [formInputs, setFormInputs] = useState<Record<string, any>>({});
  const [showToon, setShowToon] = useState(false);
  const [toonData, setToonData] = useState('');
  
  // Annotation state
  const [customName, setCustomName] = useState('');
  const [customDesc, setCustomDesc] = useState('');
  const [savingAnnotation, setSavingAnnotation] = useState(false);

  const tabs = ['Tools', 'Prompts', 'Resources', 'Roots', 'Sampling'];

  useEffect(() => {
    if (session?.user?.id) {
      fetchAllData();
    }
  }, [session]);

  const fetchAllData = async () => {
    if (!session?.user?.id) return;
    setLoading(true);
    try {
      const [toolsData, resourcesData, promptsData] = await Promise.all([
        api.getTools(session.user.id, undefined, true),
        api.getResources(session.user.id, true),
        api.getPrompts(session.user.id, true)
      ]);

      // Handle Tools
      if (toolsData && typeof toolsData === 'object' && 'tools' in toolsData) {
        setTools(toolsData.tools || []);
        if (activeTab === 'Tools') setToonData(toolsData.toon || '');
      } else {
        setTools(Array.isArray(toolsData) ? toolsData : []);
      }

      // Handle Resources
      if (resourcesData && typeof resourcesData === 'object' && 'resources' in resourcesData) {
        setResources(resourcesData.resources || []);
        if (activeTab === 'Resources') setToonData(resourcesData.toon || '');
      } else {
        setResources(Array.isArray(resourcesData) ? resourcesData : []);
      }

      // Handle Prompts
      if (promptsData && typeof promptsData === 'object' && 'prompts' in promptsData) {
        setPrompts(promptsData.prompts || []);
        if (activeTab === 'Prompts') setToonData(promptsData.toon || '');
      } else {
        setPrompts(Array.isArray(promptsData) ? promptsData : []);
      }

    } catch (error) {
      console.error('Failed to fetch inspector data:', error);
      setTools([]);
      setResources([]);
      setPrompts([]);
    } finally {
      setLoading(false);
    }
  };

  // Update TOON data when tab changes
  useEffect(() => {
    if (!loading) {
      updateToonForActiveTab();
    }
  }, [activeTab, loading]);

  const updateToonForActiveTab = async () => {
    if (!session?.user?.id) return;
    try {
      if (activeTab === 'Tools') {
        const data = await api.getTools(session.user.id, undefined, true);
        setToonData(data.toon || '');
      } else if (activeTab === 'Resources') {
        const data = await api.getResources(session.user.id, true);
        setToonData(data.toon || '');
      } else if (activeTab === 'Prompts') {
        const data = await api.getPrompts(session.user.id, true);
        setToonData(data.toon || '');
      } else {
        setToonData('');
      }
    } catch (e) {
      setToonData('');
    }
  };

  const selectTool = (tool: any) => {
    setSelectedTool(tool);
    setSelectedResource(null);
    setSelectedPrompt(null);
    setExecResult(null);
    setCustomName(tool.custom_name || '');
    setCustomDesc(tool.custom_description || '');
    
    // Initialize form inputs based on tool schema
    const definition = typeof tool.definition === 'string' ? JSON.parse(tool.definition) : (tool.definition || {});
    const properties = definition.inputSchema?.properties || {};
    const initialInputs: Record<string, any> = {};
    Object.keys(properties).forEach(key => {
      initialInputs[key] = properties[key].default || "";
    });
    setFormInputs(initialInputs);
  };

  const toggleToon = async () => {
    setShowToon(!showToon);
  };

  const extractParams = (uri: string) => {
    const matches = uri.match(/\{([^}]+)\}/g);
    if (!matches) return [];
    
    const params: string[] = [];
    matches.forEach(m => {
      // Strip brackets and prefixes (?, &, #, +, /, ., ;)
      const inner = m.slice(1, -1).replace(/^[\?\&\#\+\/\.\;\!]/, '');
      // Split by commas for combined blocks like {?query,limit}
      inner.split(',').forEach(p => {
        const cleanParam = p.replace(/\*$/, ''); // Strip * from {filepath*}
        if (cleanParam) params.push(cleanParam);
      });
    });
    return params;
  };

  const selectResource = async (res: any) => {
    setSelectedResource(res);
    setSelectedTool(null);
    setSelectedPrompt(null);
    setExecResult(null);

    if (res.is_template) {
      const params = extractParams(res.uri);
      const initialInputs: Record<string, any> = {};
      params.forEach(p => initialInputs[p] = "");
      setFormInputs(initialInputs);
    } else {
      setExecuting(true);
      try {
        const data = await api.readResource(session!.user!.id!, res.uri, res.server_url || '');
        setExecResult(data);
      } catch (error: any) {
        setExecResult({ error: error.message || 'Failed to read resource' });
      } finally {
        setExecuting(false);
      }
    }
  };

  const handleReadResource = async () => {
    if (!session?.user?.id || !selectedResource) return;
    setExecuting(true);
    setExecResult(null);
    
    let resolvedUri = selectedResource.uri;
    if (selectedResource.is_template) {
      // Find all {blocks}
      const matches = selectedResource.uri.match(/\{([^}]+)\}/g);
      if (matches) {
        matches.forEach(block => {
          const content = block.slice(1, -1);
          const isQuery = content.startsWith('?');
          const isContinuation = content.startsWith('&');
          const prefix = content.match(/^[\?\&\#\+\/\.\;\!]/)?.[0] || '';
          const paramsString = content.replace(/^[\?\&\#\+\/\.\;\!]/, '');
          const params = paramsString.split(',');

          if (isQuery || isContinuation) {
            const queryParts: string[] = [];
            params.forEach(p => {
              const cleanP = p.replace(/\*$/, '');
              // Match parameter names even if they have weird characters or escaping
              const val = formInputs[cleanP] || formInputs[p];
              if (val) queryParts.push(`${cleanP}=${encodeURIComponent(val)}`);
            });
            const replacement = queryParts.length > 0 ? (prefix + queryParts.join('&')) : '';
            resolvedUri = resolvedUri.split(block).join(replacement);
          } else {
            // Simple path replacement or other prefixes
            let replacement = '';
            params.forEach(p => {
              const cleanP = p.replace(/\*$/, '');
              const val = formInputs[cleanP] || formInputs[p];
              if (val) {
                replacement = prefix + encodeURIComponent(val);
              }
            });
            resolvedUri = resolvedUri.split(block).join(replacement);
          }
        });
      }
    }

    try {
      const data = await api.readResource(session.user.id, resolvedUri, selectedResource.server_url || '');
      setExecResult(data);
    } catch (error: any) {
      setExecResult({ error: error.message || 'Failed to read resource' });
    } finally {
      setExecuting(false);
    }
  };

  const selectPrompt = (prompt: any) => {
    setSelectedPrompt(prompt);
    setSelectedTool(null);
    setSelectedResource(null);
    setExecResult(null);
    
    // Initialize inputs for prompt arguments
    const initialInputs: Record<string, any> = {};
    (prompt.arguments || []).forEach((arg: any) => {
      initialInputs[arg.name] = arg.default || "";
    });
    setFormInputs(initialInputs);
  };

  const handlePromptGet = async () => {
    if (!session?.user?.id || !selectedPrompt) return;
    setExecuting(true);
    setExecResult(null);
    try {
      const data = await api.getPrompt(
        session.user.id, 
        selectedPrompt.name, 
        selectedPrompt.server_url || '', 
        formInputs
      );
      setExecResult(data);
    } catch (error: any) {
      setExecResult({ error: error.message || 'Failed to get prompt' });
    } finally {
      setExecuting(false);
    }
  };

  const handleSaveAnnotation = async () => {
    if (!selectedTool) return;
    setSavingAnnotation(true);
    try {
      await api.updateTool(selectedTool.id, {
        custom_name: customName,
        custom_description: customDesc
      });
      toast.success('Tool annotations updated');
      fetchAllData(); // Refresh list
    } catch (error: any) {
      toast.error('Failed to update annotations');
    } finally {
      setSavingAnnotation(false);
    }
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

  const filteredTools = Array.isArray(tools) ? tools.filter(tool => 
    tool.name.toLowerCase().includes(search.toLowerCase()) || 
    (tool.server_name || '').toLowerCase().includes(search.toLowerCase())
  ) : [];

  const filteredResources = Array.isArray(resources) ? resources.filter(res => 
    (res.name || '').toLowerCase().includes(search.toLowerCase()) || 
    (res.uri || '').toLowerCase().includes(search.toLowerCase()) ||
    (res.server_name || '').toLowerCase().includes(search.toLowerCase())
  ) : [];

  const filteredPrompts = Array.isArray(prompts) ? prompts.filter(p => 
    (p.name || '').toLowerCase().includes(search.toLowerCase()) || 
    (p.server_name || '').toLowerCase().includes(search.toLowerCase())
  ) : [];

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black h-[80vh]">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    );
  }

  // Grid View (Default)
  if (!selectedTool && !selectedResource && !selectedPrompt) {
    return (
      <div className="space-y-6 md:space-y-8 lg:space-y-10 animate-fade-in text-white bg-black w-full">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 px-2">
          <div>
            <h1 className="text-2xl md:text-3xl lg:text-4xl font-bold tracking-tight text-white uppercase italic">Inspector</h1>
            <p className="text-zinc-500 text-[10px] md:text-xs font-medium mt-0.5 uppercase tracking-widest">Explore and test your connected capabilities</p>
          </div>
          <div className="flex items-center gap-4">
            <button 
              onClick={toggleToon}
              className={`px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all border ${
                showToon ? 'bg-white text-black border-white' : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-500'
              }`}
            >
              Experimental: TOON
            </button>
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
        </div>

        {/* Sub-tabs */}
        <div className="flex items-center gap-2 p-1 bg-zinc-950 border border-zinc-900 rounded-2xl w-fit">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all ${
                activeTab === tab 
                  ? 'bg-white text-black shadow-lg shadow-white/5' 
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {activeTab === 'Tools' ? (
          <>
            {showToon ? (
              <div className="bg-zinc-950 p-8 rounded-[32px] border border-zinc-900">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">TOON Representation (Optimized for LLMs)</h3>
                  <div className="text-[10px] text-zinc-600 font-bold uppercase">Token Savings: ~45% vs JSON</div>
                </div>
                <pre className="text-xs font-mono text-zinc-300 leading-relaxed overflow-x-auto whitespace-pre p-6 bg-black rounded-2xl border border-zinc-900">
                  {toonData}
                </pre>
              </div>
            ) : filteredTools.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3 md:gap-4">
                {filteredTools.map((tool) => {
                  const definition = typeof tool.definition === 'string' ? JSON.parse(tool.definition) : (tool.definition || {});
                  return (
                    <button
                      key={tool.id}
                      onClick={() => selectTool(tool)}
                      className="bg-zinc-950 border border-zinc-900 rounded-2xl p-4 hover:border-zinc-600 transition-all group text-left relative overflow-hidden flex flex-col h-full shadow-sm hover:shadow-xl"
                    >
                      <div className="flex items-center justify-between mb-4">
                        <div className="w-8 h-8 rounded-lg border border-zinc-800 flex items-center justify-center text-zinc-600 group-hover:text-white transition-all">
                          <Box className="w-4 h-4" />
                        </div>
                        <ArrowRight className="w-3.5 h-3.5 text-zinc-800 group-hover:text-white transition-all -translate-x-1 opacity-0 group-hover:opacity-100 group-hover:translate-x-0" />
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <h3 className="text-xs md:text-sm font-bold text-white uppercase tracking-tight italic line-clamp-1">{tool.custom_name || tool.name}</h3>
                          {tool.custom_name && <div className="w-1 h-1 rounded-full bg-white shrink-0"></div>}
                        </div>
                        <p className="text-zinc-500 text-[9px] md:text-[10px] font-medium leading-relaxed line-clamp-2 italic">
                          {tool.custom_description || definition.description || 'System module providing specialized functions.'}
                        </p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-zinc-900 flex items-center justify-between">
                        <span className="text-[7px] md:text-[8px] font-bold text-zinc-600 uppercase tracking-widest truncate mr-2">{tool.server_name || 'Generic Node'}</span>
                        <span className="bg-emerald-500/10 text-emerald-500 px-1 py-0.5 rounded text-[6px] font-black uppercase tracking-tighter shrink-0">Ready</span>
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
          </>
        ) : activeTab === 'Resources' ? (
          <>
            {showToon ? (
              <div className="bg-zinc-950 p-8 rounded-[32px] border border-zinc-900">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">TOON Representation (Optimized for LLMs)</h3>
                  <div className="text-[10px] text-zinc-600 font-bold uppercase">Token Savings: ~45% vs JSON</div>
                </div>
                <pre className="text-xs font-mono text-zinc-300 leading-relaxed overflow-x-auto whitespace-pre p-6 bg-black rounded-2xl border border-zinc-900">
                  {toonData}
                </pre>
              </div>
            ) : filteredResources.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3 md:gap-4">
                {filteredResources.map((res) => (
                  <button
                    key={res.uri}
                    onClick={() => selectResource(res)}
                    className="bg-zinc-950 border border-zinc-900 rounded-2xl p-4 hover:border-zinc-600 transition-all group text-left relative overflow-hidden flex flex-col h-full shadow-sm hover:shadow-xl"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-8 h-8 rounded-lg border border-zinc-800 flex items-center justify-center text-zinc-600 group-hover:text-white transition-all">
                        <Activity className="w-4 h-4" />
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-zinc-800 group-hover:text-white transition-all -translate-x-1 opacity-0 group-hover:opacity-100 group-hover:translate-x-0" />
                    </div>
                    
                    <div className="flex-1">
                      <h3 className="text-xs md:text-sm font-bold text-white uppercase tracking-tight italic line-clamp-1 mb-1.5">{res.name}</h3>
                      <p className="text-zinc-500 text-[9px] md:text-[10px] font-medium leading-relaxed line-clamp-2 italic mb-2">
                        {res.description || 'System-wide operational rules and guidelines.'}
                      </p>
                      <div className="text-[8px] font-mono text-zinc-600 break-all line-clamp-1">
                        {res.uri}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-zinc-900 flex items-center justify-between">
                      <span className="text-[7px] md:text-[8px] font-bold text-zinc-600 uppercase tracking-widest truncate mr-2">{res.server_name || 'Generic Node'}</span>
                      <span className={`px-1 py-0.5 rounded text-[6px] font-black uppercase tracking-tighter shrink-0 ${res.is_template ? 'bg-amber-500/10 text-amber-500' : 'bg-blue-500/10 text-blue-500'}`}>
                        {res.is_template ? 'Template' : 'Static'}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-24 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-[32px]">
                <div className="text-3xl font-bold mb-2">No Results</div>
                <p className="text-sm font-medium uppercase tracking-widest">Adjust filters to find resource</p>
              </div>
            )}
          </>
        ) : activeTab === 'Prompts' ? (
          <>
            {showToon ? (
              <div className="bg-zinc-950 p-8 rounded-[32px] border border-zinc-900">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">TOON Representation (Optimized for LLMs)</h3>
                  <div className="text-[10px] text-zinc-600 font-bold uppercase">Token Savings: ~45% vs JSON</div>
                </div>
                <pre className="text-xs font-mono text-zinc-300 leading-relaxed overflow-x-auto whitespace-pre p-6 bg-black rounded-2xl border border-zinc-900">
                  {toonData}
                </pre>
              </div>
            ) : filteredPrompts.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3 md:gap-4">
                {filteredPrompts.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => selectPrompt(p)}
                    className="bg-zinc-950 border border-zinc-900 rounded-2xl p-4 hover:border-zinc-600 transition-all group text-left relative overflow-hidden flex flex-col h-full shadow-sm hover:shadow-xl"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-8 h-8 rounded-lg border border-zinc-800 flex items-center justify-center text-zinc-600 group-hover:text-white transition-all">
                        <Search className="w-4 h-4" />
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-zinc-800 group-hover:text-white transition-all -translate-x-1 opacity-0 group-hover:opacity-100 group-hover:translate-x-0" />
                    </div>
                    
                    <div className="flex-1">
                      <h3 className="text-xs md:text-sm font-bold text-white uppercase tracking-tight italic line-clamp-1 mb-1.5">{p.name}</h3>
                      <p className="text-zinc-500 text-[9px] md:text-[10px] font-medium leading-relaxed line-clamp-2 italic">
                        {p.description || 'System prompt for specialized LLM interaction.'}
                      </p>
                    </div>

                    <div className="mt-4 pt-3 border-t border-zinc-900 flex items-center justify-between">
                      <span className="text-[7px] md:text-[8px] font-bold text-zinc-600 uppercase tracking-widest truncate mr-2">{p.server_name || 'Generic Node'}</span>
                      <span className="bg-purple-500/10 text-purple-500 px-1 py-0.5 rounded text-[6px] font-black uppercase tracking-tighter shrink-0">Prompt</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-24 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-[32px]">
                <div className="text-3xl font-bold mb-2">No Results</div>
                <p className="text-sm font-medium uppercase tracking-widest">Adjust filters to find prompt</p>
              </div>
            )}
          </>
        ) : (
          <div className="py-32 text-center border-2 border-dashed border-zinc-900 rounded-[40px] bg-zinc-950/50">
            <div className="w-20 h-20 bg-zinc-900 border border-zinc-800 rounded-3xl flex items-center justify-center mx-auto mb-8">
              <Activity className="w-10 h-10 text-zinc-700" />
            </div>
            <h2 className="text-2xl font-bold text-white uppercase italic mb-2">{activeTab} Coming Soon</h2>
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-[0.3em]">Module being calibrated for production</p>
          </div>
        )}
      </div>
    );
  }

  // Detail / Testing View
  const selectedItem = selectedTool || selectedResource || selectedPrompt;
  const isTool = !!selectedTool;
  const isResource = !!selectedResource;
  const isPrompt = !!selectedPrompt;

  const definition = isTool 
    ? (typeof selectedTool.definition === 'string' ? JSON.parse(selectedTool.definition) : (selectedTool.definition || {}))
    : {};
  const properties = isTool ? (definition.inputSchema?.properties || {}) : {};

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col animate-fade-in bg-black text-white">
      <div className="flex items-center justify-between mb-8 shrink-0">
        <div className="flex items-center gap-6">
          <button 
            onClick={() => {
              setSelectedTool(null);
              setSelectedResource(null);
              setSelectedPrompt(null);
            }}
            className="w-12 h-12 bg-zinc-950 border border-zinc-900 rounded-2xl flex items-center justify-center text-zinc-500 hover:text-white hover:border-zinc-700 transition-all shadow-sm"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <span className="bg-zinc-900 text-zinc-500 px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest">
                {isTool ? 'Tool' : isResource ? 'Resource' : 'Prompt'}::{selectedItem.name}
              </span>
            </div>
            <h1 className="text-4xl font-bold tracking-tighter text-white mt-1 uppercase italic">{selectedItem.name}</h1>
          </div>
        </div>
        <div className="flex items-center gap-3 text-zinc-500 bg-zinc-950 border border-zinc-900 px-5 py-2.5 rounded-2xl">
          <Terminal className="w-4 h-4" />
          <span className="text-[10px] font-bold uppercase tracking-widest truncate max-w-[300px]">{selectedItem.server_url || selectedItem.uri}</span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden grid grid-cols-12 gap-8">
        {/* Left Column: Details & Inputs */}
        <div className="col-span-12 lg:col-span-4 flex flex-col space-y-8 overflow-y-auto pr-4 custom-scrollbar min-h-0">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[32px] p-10 space-y-10">
            {isTool && (
              <div className="space-y-6">
                <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.3em] flex items-center gap-2">
                  <Box className="w-3.5 h-3.5" />
                  LLM Context
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest mb-1.5 block">Custom Name (Alias)</label>
                    <input 
                      type="text" 
                      value={customName}
                      onChange={e => setCustomName(e.target.value)}
                      placeholder={selectedTool.name}
                      className="w-full bg-black border border-zinc-900 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-zinc-500 transition-all font-medium"
                    />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest mb-1.5 block">Custom Description</label>
                    <textarea 
                      rows={2}
                      value={customDesc}
                      onChange={e => setCustomDesc(e.target.value)}
                      placeholder={definition.description || "Contextual hint for LLM..."}
                      className="w-full bg-black border border-zinc-900 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-zinc-500 transition-all font-medium resize-none"
                    />
                  </div>
                  <button 
                    onClick={handleSaveAnnotation}
                    disabled={savingAnnotation}
                    className="w-full bg-white text-black py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-widest hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50"
                  >
                    {savingAnnotation ? 'SAVING...' : 'Update Context'}
                  </button>
                </div>
              </div>
            )}

            <div className={`${isTool ? 'pt-10 border-t border-zinc-900' : ''} space-y-4`}>
              <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.3em] flex items-center gap-2">
                <Info className="w-3.5 h-3.5" />
                Documentation
              </h3>
              <p className="text-zinc-400 text-lg font-medium leading-relaxed italic">
                {isTool ? (definition.description || 'System module providing specialized functions.') : selectedItem.description}
              </p>
            </div>

            {(isTool || isPrompt || (isResource && selectedResource.is_template)) && (
              <div className="pt-10 border-t border-zinc-900 space-y-10">
                <h3 className="text-[10px] font-bold text-zinc-600 uppercase tracking-[0.3em] flex items-center gap-2">
                  <Wrench className="w-3.5 h-3.5" />
                  Parameters
                </h3>
                
                <div className="space-y-8">
                  {isTool && Object.keys(properties).length > 0 ? (
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
                  ) : isPrompt && selectedPrompt.arguments?.length > 0 ? (
                    selectedPrompt.arguments.map((arg: any) => (
                      <div key={arg.name} className="space-y-3">
                        <div className="flex items-center justify-between">
                          <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest italic">{arg.name}</label>
                          {arg.required && <span className="text-[9px] font-black text-red-800 uppercase tracking-widest">Required</span>}
                        </div>
                        <input 
                          type="text"
                          placeholder={`_INPUT_${arg.name.toUpperCase()}_`}
                          className="w-full bg-black border border-zinc-900 rounded-2xl p-5 text-sm font-bold text-white outline-none focus:border-white transition-all placeholder:text-zinc-900 uppercase"
                          value={formInputs[arg.name] || ''}
                          onChange={(e) => setFormInputs({...formInputs, [arg.name]: e.target.value})}
                        />
                        {arg.description && <p className="text-[9px] text-zinc-700 font-bold uppercase tracking-tight italic opacity-50">{arg.description}</p>}
                      </div>
                    ))
                  ) : isResource && selectedResource.is_template ? (
                    extractParams(selectedResource.uri).map((param: string) => (
                      <div key={param} className="space-y-3">
                        <div className="flex items-center justify-between">
                          <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest italic">{param}</label>
                          <span className="text-[9px] font-black text-amber-800 uppercase tracking-widest">Template_Var</span>
                        </div>
                        <input 
                          type="text"
                          placeholder={`_FILL_${param.toUpperCase()}_`}
                          className="w-full bg-black border border-zinc-900 rounded-2xl p-5 text-sm font-bold text-white outline-none focus:border-white transition-all placeholder:text-zinc-900 uppercase"
                          value={formInputs[param] || ''}
                          onChange={(e) => setFormInputs({...formInputs, [param]: e.target.value})}
                        />
                      </div>
                    ))
                  ) : (
                    <div className="p-12 text-center text-zinc-800 border-2 border-dashed border-zinc-900 rounded-3xl text-[10px] font-bold uppercase tracking-widest">
                      No variables required
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Results & Logs */}
        <div className="col-span-12 lg:col-span-8 flex flex-col space-y-8 h-full overflow-hidden min-h-0">
          <div className="flex-1 bg-zinc-950 border border-zinc-900 rounded-[32px] flex flex-col overflow-hidden shadow-2xl relative">
            <div className="p-8 border-b border-zinc-900 flex items-center justify-between shrink-0 bg-zinc-950/50 backdrop-blur-sm z-10">
              <div className="flex items-center gap-4">
                {(isTool || isPrompt || (isResource && selectedResource.is_template)) && (
                  <button 
                    onClick={isTool ? handleExecute : isPrompt ? handlePromptGet : handleReadResource}
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
                        {isTool ? 'Execute Tool' : isPrompt ? 'Get Prompt' : 'Read Resource'}
                      </>
                    )}
                  </button>
                )}

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
                  {(isTool || isPrompt || (isResource && selectedResource.is_template)) && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-3 opacity-50">
                        <ArrowUpRight className="w-3 h-3" />
                        <span className="text-[9px] font-black uppercase tracking-[0.2em]">
                          {isResource ? 'Resolved_URI' : 'Request_Payload'}
                        </span>
                      </div>
                      <div className="bg-black/50 border border-zinc-900 rounded-2xl p-6 shadow-inner">
                        <pre className="text-[11px] font-mono text-zinc-500 whitespace-pre-wrap leading-relaxed">
                          {isResource ? (() => {
                            let resolvedUri = selectedResource.uri;
                            Object.entries(formInputs).forEach(([key, value]) => {
                              resolvedUri = resolvedUri.replace(new RegExp(`\\{${key}\\*?\\}`, 'g'), value || `{${key}}`);
                            });
                            return resolvedUri;
                          })() : JSON.stringify({ params: formInputs }, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

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
                          <div className="text-sm font-bold text-zinc-500 uppercase tracking-[0.8em] italic">
                            {isResource ? 'Calibrating_Resource' : 'Waiting_for_Action'}
                          </div>
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
