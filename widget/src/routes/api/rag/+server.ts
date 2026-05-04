/**
 * SynapseOS SSE Proxy — SvelteKit Server Endpoint
 * Proxies RAG queries from browser to SynapseOS API.
 * Hides API key from client, avoids CORS issues.
 */
import type { RequestHandler } from './$types';
import { SYNAPSE_URL, SYNAPSE_KEY } from '$env/static/private';

export const POST: RequestHandler = async ({ request }) => {
  const body = await request.json();

  // Handle feedback action
  if (body.action === 'feedback') {
    const resp = await fetch(`${SYNAPSE_URL}/v1/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': body.tenant_id || 'default',
        'Authorization': `Bearer ${SYNAPSE_KEY}`,
      },
      body: JSON.stringify({
        trace_id: body.trace_id,
        rating: body.rating,
      }),
    });
    return new Response(resp.ok ? 'OK' : 'Error', { status: resp.status });
  }

  const useThink = body.use_think === true;
  const endpoint = useThink ? '/v1/think' : '/v1/query';
  const tenantId = body.tenant_id || 'default';

  // Build request payload
  const payload: Record<string, any> = {
    question: body.question,
    stream: useThink ? false : true, // Think mode: non-streaming (collects full result)
  };

  if (useThink) {
    payload.session_id = body.session_id || `widget-${Date.now()}`;
    payload.user_id = body.user_id || 'widget-user';
  }

  // Forward to SynapseOS API
  const resp = await fetch(`${SYNAPSE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-ID': tenantId,
      'Authorization': `Bearer ${SYNAPSE_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    return new Response(JSON.stringify({ error: `API error: ${resp.status}` }), {
      status: resp.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // For Think mode: return JSON directly
  if (useThink) {
    const data = await resp.json();
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // For streaming: re-stream SSE chunks to browser
  return new Response(resp.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
};
