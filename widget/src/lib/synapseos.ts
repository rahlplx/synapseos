/**
 * SynapseOS Client Singleton for SvelteKit
 * Reads config from environment variables at module level.
 */
import SynapseOSClient from '@synapseos/sdk';

const SYNAPSE_URL = import.meta.env.VITE_SYNAPSE_URL || '';
const SYNAPSE_KEY = import.meta.env.VITE_SYNAPSE_KEY || '';
const TENANT_ID = import.meta.env.VITE_TENANT_ID || 'default';

let _client: SynapseOSClient | null = null;

export function getSynapseClient(): SynapseOSClient {
  if (!_client) {
    if (!SYNAPSE_URL) {
      throw new Error('VITE_SYNAPSE_URL is not set. Check your .env file.');
    }
    _client = new SynapseOSClient({
      baseUrl: SYNAPSE_URL,
      apiKey: SYNAPSE_KEY,
      tenantId: TENANT_ID,
    });
  }
  return _client;
}
