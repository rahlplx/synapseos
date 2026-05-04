/**
 * SynapseOS Edge Proxy — Cloudflare Workers
 * SHA-256 KV cache with tenant isolation. Cache hit < 50ms. Miss → Oracle ARM backend.
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

    // Clone request body for cache key computation
    const cloned = request.clone();
    const body = await cloned.text();

    // Streaming requests bypass cache — they can't be cached as complete responses
    if (body.includes('"stream":true') || body.includes('"stream": true')) {
      return fetch(env.ORACLE_BACKEND + url.pathname, request);
    }

    // SHA-256 hash of body + tenant ID — prevents cross-tenant cache pollution
    const tenantId = request.headers.get("X-Tenant-ID") ?? "";
    const hashBuf = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(body + tenantId),
    );
    const cacheKey = Array.from(new Uint8Array(hashBuf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    // Check KV cache — O(1) lookup
    const cached = await env.RAG_CACHE.get(cacheKey);
    if (cached) {
      return new Response(cached, {
        headers: {
          "Content-Type": "application/json",
          "X-Cache-Status": "HIT",
          "X-Cache-Key": cacheKey.slice(0, 8),
        },
      });
    }

    // Cache miss — forward to Oracle ARM backend
    const backendResp = await fetch(
      env.ORACLE_BACKEND + url.pathname,
      new Request(request, { body }),
    );

    // Only cache successful non-streaming responses
    if (backendResp.ok) {
      const respClone = backendResp.clone();
      const respText = await respClone.text();
      await env.RAG_CACHE.put(cacheKey, respText, {
        expirationTtl: env.CACHE_TTL ?? 3600,
      });
    }

    // Add MISS header to response
    const headers = new Headers(backendResp.headers);
    headers.set("X-Cache-Status", "MISS");
    return new Response(backendResp.body, {
      status: backendResp.status,
      headers,
    });
  },
};
