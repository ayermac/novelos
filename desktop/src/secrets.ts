import { safeStorage } from 'electron';
import * as fs from 'fs';
import * as path from 'path';
import { log } from './logging';

interface SecretEntry {
  encrypted: string;
  updated_at: string;
  storage: 'electron_safe_storage';
}

interface SecretsFile {
  [envName: string]: SecretEntry;
}

function getSecretsPath(configDir: string): string {
  return path.join(configDir, 'secrets.json');
}

function readSecrets(configDir: string): SecretsFile {
  const filePath = getSecretsPath(configDir);
  if (!fs.existsSync(filePath)) {
    return {};
  }
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const parsed = JSON.parse(raw) as SecretsFile;
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function writeSecrets(configDir: string, secrets: SecretsFile): void {
  const filePath = getSecretsPath(configDir);
  fs.writeFileSync(filePath, JSON.stringify(secrets, null, 2), 'utf-8');
  try {
    if (process.platform !== 'win32') {
      fs.chmodSync(filePath, 0o600);
    }
  } catch {
    // ignore chmod failures
  }
}

function validateEnvName(envName: string): void {
  if (!envName) {
    throw new Error('envName is required');
  }
  if (!/^[A-Z0-9_]+$/.test(envName)) {
    throw new Error('envName must contain only uppercase letters, digits, and underscores');
  }
  if (!envName.endsWith('_API_KEY')) {
    throw new Error('envName must end with _API_KEY');
  }
}

export function setApiKey(configDir: string, envName: string, value: string): void {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Electron safeStorage encryption is not available on this system');
  }
  validateEnvName(envName);
  if (!value || value.trim().length === 0) {
    throw new Error('value must not be empty');
  }
  const secrets = readSecrets(configDir);
  const encrypted = safeStorage.encryptString(value.trim()).toString('base64');
  secrets[envName] = {
    encrypted,
    updated_at: new Date().toISOString(),
    storage: 'electron_safe_storage',
  };
  writeSecrets(configDir, secrets);
  log('info', `Stored encrypted API key for ${envName}`);
}

export function deleteApiKey(configDir: string, envName: string): void {
  validateEnvName(envName);
  const secrets = readSecrets(configDir);
  if (secrets[envName]) {
    delete secrets[envName];
    writeSecrets(configDir, secrets);
    log('info', `Deleted API key for ${envName}`);
  }
}

export function hasApiKey(configDir: string, envName: string): boolean {
  const secrets = readSecrets(configDir);
  return !!secrets[envName];
}

export function getApiKeyForSidecar(configDir: string, envName: string): string | null {
  if (!safeStorage.isEncryptionAvailable()) {
    return null;
  }
  const secrets = readSecrets(configDir);
  const entry = secrets[envName];
  if (!entry) {
    return null;
  }
  try {
    const encryptedBuffer = Buffer.from(entry.encrypted, 'base64');
    return safeStorage.decryptString(encryptedBuffer);
  } catch (err) {
    log('error', `Failed to decrypt secret for ${envName}: ${(err as Error).message}`);
    return null;
  }
}

export function listSecretStatuses(configDir: string): Record<string, { configured: boolean; storage: 'electron_safe_storage' }> {
  const secrets = readSecrets(configDir);
  const result: Record<string, { configured: boolean; storage: 'electron_safe_storage' }> = {};
  for (const envName of Object.keys(secrets)) {
    result[envName] = { configured: true, storage: 'electron_safe_storage' };
  }
  return result;
}
