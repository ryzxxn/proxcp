import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  getServers: (userId: string) => 
    apiClient.get(`/${userId}/servers`, { params: { user_id: userId } }).then(res => res.data),
  
  addServer: (userId: string, data: any) => 
    apiClient.post(`/${userId}/servers`, data, { params: { user_id: userId } }).then(res => res.data),
  
  deleteServer: (userId: string, serverId: string) => 
    apiClient.delete(`/${userId}/servers/${serverId}`, { params: { user_id: userId } }).then(res => res.data),
  
  getServerStatus: (userId: string, serverId: string) =>
    apiClient.get(`/${userId}/servers/${serverId}/status`, { params: { user_id: userId } }).then(res => res.data),

  syncServers: (userId: string) => 
    apiClient.post(`/${userId}/synchronize`, {}, { params: { user_id: userId } }).then(res => res.data),
  
  getTools: (userId: string) => 
    apiClient.get('/tools', { params: { user_id: userId } }).then(res => res.data),
  
  getApiKeys: (userId: string) => 
    apiClient.get('/api_key', { params: { user_id: userId } }).then(res => res.data),
  
  createApiKey: (userId: string, name: string) => 
    apiClient.post('/api_key', { user_id: userId, name }, { params: { user_id: userId } }).then(res => res.data),
  
  deleteApiKey: (userId: string, keyId: string) => 
    apiClient.delete(`/api_key/${keyId}`, { params: { user_id: userId } }).then(res => res.data),
  
  getApiKeyTools: (userId: string, toolConfigId: string) =>
    apiClient.get(`/api_key/${toolConfigId}/tools`, { params: { user_id: userId } }).then(res => res.data),

  addToolToApiKey: (userId: string, toolConfigId: string, toolId: string) =>
    apiClient.post(`/api_key/${toolConfigId}/tools`, { tool_id: toolId }, { params: { user_id: userId } }).then(res => res.data),

  removeToolFromApiKey: (userId: string, toolConfigId: string, mappingId: string) =>
    apiClient.delete(`/api_key/${toolConfigId}/tools/${mappingId}`, { params: { user_id: userId } }).then(res => res.data),

  syncAllToolsToApiKey: (userId: string, toolConfigId: string) =>
    apiClient.post(`/api_key/${toolConfigId}/sync`, {}, { params: { user_id: userId } }).then(res => res.data),

  toggleApiKey: (userId: string, keyId: string, active: boolean) =>
    apiClient.post(`/api_key/${keyId}/activate`, { active }, { params: { user_id: userId } }).then(res => res.data),

  getTransactions: (userId: string) => 
    apiClient.get('/transactions', { params: { user_id: userId } }).then(res => res.data),
  
  getToolUsage: (userId: string) => 
    apiClient.get('/transactions/tool_usage', { params: { user_id: userId } }).then(res => res.data),

  executeTool: (data: { user_id: string; session_id: string; tool_name: string; server_url?: string; params: any }) =>
    apiClient.post('/execute', data, { params: { user_id: data.user_id } }).then(res => res.data),
};
