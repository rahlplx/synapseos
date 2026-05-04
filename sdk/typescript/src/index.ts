/**
 * SynapseOS TypeScript SDK — BYOK RAG with cognitive engine
 * Install: npm install @synapseos/sdk
 */
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

export class SynapseOSClient {
  private base: string;
  private headers: HeadersInit;

  constructor(config: { baseUrl: string; apiKey: string; tenantId: string }) {
    this.base = config.baseUrl.replace(/\/$/, "") + "/v1";
    this.headers = {
      "Authorization": `Bearer ${config.apiKey}`,
      "X-Tenant-ID": config.tenantId,
      "Content-Type": "application/json",
    };
  }

  /** Non-streaming RAG query. Returns full answer with sources. */
  async query(question: string, topK = 5, useHyde = false): Promise<QueryResult> {
    const resp = await fetch(`${this.base}/query`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ question, top_k: topK, stream: false, use_hyde: useHyde }),
    });
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
    const resp = await fetch(`${this.base}/query`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ question, top_k: topK, stream: true, use_hyde: useHyde }),
    });
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

  /** Full cognitive query with memory + reasoning + tools + reflection. */
  async think(question: string, sessionId: string, userId: string): Promise<ThinkResult> {
    const resp = await fetch(`${this.base}/think`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ question, session_id: sessionId, user_id: userId, stream: false }),
    });
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

  /** Queue document ingestion. Returns job ID immediately. */
  async ingest(urls: string[], metadata?: Record<string, string>): Promise<IngestJob> {
    const resp = await fetch(`${this.base}/ingest`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ urls, metadata }),
    });
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    const d = await resp.json();
    return { jobId: d.job_id, status: d.status };
  }

  /** Submit thumbs up (+1) or thumbs down (-1) on a response. */
  async feedback(traceId: string, rating: 1 | -1): Promise<void> {
    const resp = await fetch(`${this.base}/feedback`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ trace_id: traceId, rating }),
    });
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
  }

  /** Get collection stats for the tenant. */
  async collections(): Promise<Record<string, any>> {
    const resp = await fetch(`${this.base}/collections`, {
      method: "GET",
      headers: this.headers,
    });
    if (!resp.ok) {
      throw new Error(`SynapseOS error: ${resp.status}`);
    }
    return resp.json();
  }
}
