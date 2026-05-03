/**
 * SynapseOS Edge Proxy — Cloudflare Workers
 * SHA-256 KV cache. Cache hit < 50ms. Miss → Oracle ARM backend.
 * Deploy: wrangler deploy cloudflare/worker.ts --name synapseos-edge
 */
export interface Env {
  RAG_CACHE: KVNamespace;
  ORACLE_BACKEND: string;
  CACHE_TTL: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only cache POST /v1/query (non-streaming)
    if (request.method !== "POST" || !url.pathname.includes("/query")) {
      return fetch(env.ORACLE_BACKEND + url.pathname, request);
    }

    const cloned = request.clone();
    const body = await cloned.text();
    if (body.includes('"stream":true')) {
      return fetch(env.ORACLE_BACKEND + url.pathname, request);
    }

    const hashBuf = await crypto.subtle.digest("SHA-256",
      new TextEncoder().encode(body + (request.headers.get("X-Tenant-ID") ?? "")));
    const key = Array.from(new Uint8Array(hashBuf)).map(b => b.toString(16).padStart(2, "0")).join("");

    const cached = await env.RAG_CACHE.get(key);
    if (cached) {
      return new Response(cached, { headers: { "Content-Type": "application/json", "X-Cache": "HIT" } });
    }

    const resp = await fetch(env.ORACLE_BACKEND + url.pathname, new Request(request, { body }));
    if (resp.ok) {
      const text = await resp.clone().text();
      await env.RAG_CACHE.put(key, text, { expirationTtl: env.CACHE_TTL ?? 3600 });
    }
    return resp;
  },
};
