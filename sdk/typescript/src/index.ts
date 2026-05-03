export interface QueryResult { answer: string; sources: Source[]; traceId: string; }
export interface Source { text: string; score: number; sourceUrl?: string; }

export class SynapseOSClient {
  private base: string;
  private headers: HeadersInit;

  constructor(config: { baseUrl: string; apiKey: string; tenantId: string }) {
    this.base = config.baseUrl.replace(/\/$/, "") + "/v1";
    this.headers = { "Authorization": `Bearer ${config.apiKey}`, "X-Tenant-ID": config.tenantId, "Content-Type": "application/json" };
  }

  async query(question: string, topK = 5): Promise<QueryResult> {
    const resp = await fetch(`${this.base}/query`, { method: "POST", headers: this.headers, body: JSON.stringify({ question, top_k: topK, stream: false }) });
    if (!resp.ok) throw new Error(`SynapseOS error: ${resp.status}`);
    const d = await resp.json();
    return { answer: d.answer, sources: d.sources, traceId: d.trace_id };
  }

  async *queryStream(question: string): AsyncGenerator<string> {
    const resp = await fetch(`${this.base}/query`, { method: "POST", headers: this.headers, body: JSON.stringify({ question, stream: true }) });
    if (!resp.body) throw new Error("No body");
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) { const p = JSON.parse(line.slice(6)); if (p.chunk) yield p.chunk; if (p.done) return; }
      }
    }
  }

  async ingest(urls: string[], metadata?: Record<string, string>) {
    const resp = await fetch(`${this.base}/ingest`, { method: "POST", headers: this.headers, body: JSON.stringify({ urls, metadata }) });
    return resp.json();
  }

  async feedback(traceId: string, rating: 1 | -1) {
    await fetch(`${this.base}/feedback`, { method: "POST", headers: this.headers, body: JSON.stringify({ trace_id: traceId, rating }) });
  }
}
