/**
 * SynapseOS TypeScript SDK — BYOK RAG with cognitive engine
 * Includes automatic retry with exponential backoff on transient failures.
 * Install: npm install @synapseos/sdk
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface QueryResult {
  answer: string;
  sources: Source[];
  traceId: string;
  latencyMs: number;
}

export interface Source {
  chunkId: string;
  text: string;
  score: number;
  sourceUrl?: string;
}

export interface ThinkResult {
  answer: string;
  queryType: string;
  stepsTaken: number;
  reflectionScores: Record<string, number>;
  memoriesRecalled: number;
  toolsUsed: string[];
  traceId: string;
}

export interface IngestJob {
  jobId: string;
  status: string;
}

export interface RetryConfig {
  maxRetries: number;   // Default: 3
  baseDelay: number;    // Base delay in ms, default: 1000
}

// ─── Retry Logic ─────────────────────────────────────────────────────────────

const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

function shouldRetry(resp?: Response, error?: unknown): boolean {
  if (error) {
    // Retry on network errors (TypeError from fetch failures)
    return error instanceof TypeError || error instanceof DOMException;
  }
  if (resp) {
    return RETRYABLE_STATUS.has(resp.status);
  }
  return false;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retryConfig: RetryConfig,
): Promise<Response> {
  const { maxRetries, baseDelay } = retryConfig;
  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const resp = await fetch(url, options);

      if (!resp.ok && shouldRetry(resp) && attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt);
        console.warn(
          `[SynapseOS retry] Attempt ${attempt + 1}/${maxRetries + 1} failed: ` +
          `${resp.status} ${resp.statusText}. Retrying in ${delay}ms...`
        );
        await sleep(delay);
        continue;
      }

      return resp;
    } catch (error) {
      lastError = error;
      if (shouldRetry(undefined, error) && attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt);
        console.warn(
          `[SynapseOS retry] Attempt ${attempt + 1}/${maxRetries + 1} failed: ` +
          `${error}. Retrying in ${delay}ms...`
        );
        await sleep(delay);
        continue;
      }
      throw error;
    }
  }

  throw lastError;
}

// ─── Client ──────────────────────────────────────────────────────────────────

export class SynapseOSClient {
  private base: string;
  private headers: HeadersInit;
  private retryConfig: RetryConfig;

  constructor(
    config: { baseUrl: string; apiKey: string; tenantId: string },
    retryConfig?: Partial<RetryConfig>,
  ) {
    this.base = config.baseUrl.replace(/\/$/, "") + "/v1";
    this.headers = {
      "Authorization": `Bearer ${config.apiKey}`,
      "X-Tenant-ID": config.tenantId,
      "Content-Type": "application/json",
    };
    this.retryConfig = {
      maxRetries: retryConfig?.maxRetries ?? 3,
      baseDelay: retryConfig?.baseDelay ?? 1000,
    };
  }

  /** Non-streaming RAG query. Returns full answer with sources. Auto-retries on transient failures. */
  async query(question: string, topK = 5, useHyde = false): Promise<QueryResult> {
    const resp = await fetchWithRetry(
      `${this.base}/query`,
      {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ question, top_k: topK, stream: false, use_hyde: useHyde }),
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status} ${await resp.text()}`);
    }
    const d = await resp.json();
    return {
      answer: d.answer,
      sources: (d.sources || []).map((s: any) => ({
        chunkId: s.chunk_id || "",
        text: s.text || "",
        score: s.score || 0,
        sourceUrl: s.source_url,
      })),
      traceId: d.trace_id || "",
      latencyMs: d.latency_ms || 0,
    };
  }

  /** Streaming RAG query. Yields answer chunks in real-time via SSE. */
  async *queryStream(question: string, topK = 5, useHyde = false): AsyncGenerator<string> {
    const resp = await fetchWithRetry(
      `${this.base}/query`,
      {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ question, top_k: topK, stream: true, use_hyde: useHyde }),
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    if (!resp.body) throw new Error("No response body");

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += dec.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // Keep incomplete line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        try {
          const payload = JSON.parse(trimmed.slice(6));
          if (payload.chunk) yield payload.chunk;
          if (payload.done) return;
        } catch {
          // Skip malformed JSON lines
          continue;
        }
      }
    }
  }

  /** Full cognitive query with memory + reasoning + tools + reflection. Auto-retries on transient failures. */
  async think(question: string, sessionId: string, userId: string): Promise<ThinkResult> {
    const resp = await fetchWithRetry(
      `${this.base}/think`,
      {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ question, session_id: sessionId, user_id: userId, stream: false }),
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    const d = await resp.json();
    return {
      answer: d.answer,
      queryType: d.query_type || "simple",
      stepsTaken: d.steps_taken || 1,
      reflectionScores: d.reflection_scores || {},
      memoriesRecalled: d.memories_recalled || 0,
      toolsUsed: d.tools_used || [],
      traceId: d.trace_id || "",
    };
  }

  /** Queue document ingestion. Returns job ID immediately. Auto-retries on transient failures. */
  async ingest(urls: string[], metadata?: Record<string, string>): Promise<IngestJob> {
    const resp = await fetchWithRetry(
      `${this.base}/ingest`,
      {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ urls, metadata }),
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    const d = await resp.json();
    return { jobId: d.job_id, status: d.status };
  }

  /** Submit thumbs up (+1) or thumbs down (-1) on a response. */
  async feedback(traceId: string, rating: 1 | -1): Promise<void> {
    const resp = await fetchWithRetry(
      `${this.base}/feedback`,
      {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ trace_id: traceId, rating }),
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
  }

  /** Get collection stats for the tenant. */
  async collections(): Promise<Record<string, any>> {
    const resp = await fetchWithRetry(
      `${this.base}/collections`,
      {
        method: "GET",
        headers: this.headers,
      },
      this.retryConfig,
    );
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    return resp.json();
  }
}
