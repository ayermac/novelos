/**
 * Desktop-first-run LLM provider presets.
 *
 * These presets only provide configuration templates (base URL, model, env name).
 * Actual API keys are never stored here; they go through Electron safeStorage.
 */

export interface DesktopProviderPreset {
  id: string
  label: string
  baseUrl: string
  model: string
  apiKeyEnv: string
  helperText: string
}

export const DESKTOP_PROVIDER_PRESETS: DesktopProviderPreset[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    apiKeyEnv: 'OPENAI_API_KEY',
    helperText: 'OpenAI 官方 API，支持 GPT-4o、GPT-4o-mini 等模型。',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    apiKeyEnv: 'DEEPSEEK_API_KEY',
    helperText: 'DeepSeek 官方 API，支持 deepseek-chat、deepseek-reasoner 等模型。',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'openai/gpt-4o-mini',
    apiKeyEnv: 'OPENROUTER_API_KEY',
    helperText: 'OpenRouter 聚合平台，支持多家模型提供商。',
  },
  {
    id: 'ark',
    label: '火山 Ark / 豆包兼容接口',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    model: '',
    apiKeyEnv: 'OPENAI_API_KEY',
    helperText: '字节跳动火山引擎 Ark 平台。请从 Ark 控制台获取 Endpoint ID 填入模型字段。',
  },
  {
    id: 'custom',
    label: '自定义 OpenAI 兼容接口',
    baseUrl: '',
    model: '',
    apiKeyEnv: 'OPENAI_API_KEY',
    helperText: '任何兼容 OpenAI API 格式的自定义接口。请填写 Base URL 和模型 ID。',
  },
]

export function getPresetById(id: string): DesktopProviderPreset | undefined {
  return DESKTOP_PROVIDER_PRESETS.find((p) => p.id === id)
}
