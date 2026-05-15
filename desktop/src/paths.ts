import * as path from 'path';
import * as fs from 'fs';
import { app } from 'electron';

export function getUserDataPath(): string {
  return app.getPath('userData');
}

export interface AppDirectories {
  dataDir: string;
  configDir: string;
  logsDir: string;
  backupsDir: string;
}

export function ensureAppDirectories(): AppDirectories {
  const userData = getUserDataPath();
  const dirs: AppDirectories = {
    dataDir: path.join(userData, 'data'),
    configDir: path.join(userData, 'config'),
    logsDir: path.join(userData, 'logs'),
    backupsDir: path.join(userData, 'backups'),
  };

  for (const dir of Object.values(dirs)) {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  return dirs;
}

const DEFAULT_CONFIG_CONTENT = `# Novelos Desktop Default Config
# Generated automatically. Safe to edit.

# LLM mode: stub = demo mode, real = call external API
llm_mode: stub

# Default LLM profile (no API key stored here)
llm_profiles:
  default:
    provider: openai_compatible
    model: gpt-4
    base_url: "https://api.openai.com/v1"
    api_key_env: OPENAI_API_KEY
    temperature: 0.7
    max_tokens: 4096

default_llm: default
`;

export function ensureDefaultConfig(configDir: string): void {
  const configPath = path.join(configDir, 'local.yaml');
  if (!fs.existsSync(configPath)) {
    try {
      fs.writeFileSync(configPath, DEFAULT_CONFIG_CONTENT, 'utf-8');
    } catch {
      // Silent fail — sidecar will run without config
    }
  }
}
