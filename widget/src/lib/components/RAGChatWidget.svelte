<script lang="ts">
  /**
   * SynapseOS RAG Chat Widget — SvelteKit Component
   * Streaming chat with Think mode, source display, and feedback.
   * Uses SynapseOSClient from @synapseos/sdk via SSE proxy.
   */
  import { onMount } from 'svelte';

  interface Source {
    chunk_id: string;
    text: string;
    score: number;
    source_url?: string;
  }

  interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: Source[];
    traceId?: string;
    feedbackGiven?: 'up' | 'down' | null;
    queryType?: string;
    memoriesRecalled?: number;
    toolsUsed?: string[];
  }

  let messages: Message[] = [];
  let input = '';
  let isStreaming = false;
  let thinkMode = false;
  let chatContainer: HTMLDivElement;

  const SYNAPSE_URL = import.meta.env.VITE_SYNAPSE_URL || '';
  const SYNAPSE_KEY = import.meta.env.VITE_SYNAPSE_KEY || '';
  const TENANT_ID = import.meta.env.VITE_TENANT_ID || 'default';

  onMount(() => {
    chatContainer?.scrollTo(0, chatContainer.scrollHeight);
  });

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (chatContainer) {
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
      }
    });
  }

  async function sendMessage() {
    const question = input.trim();
    if (!question || isStreaming) return;

    messages = [...messages, { role: 'user', content: question }];
    input = '';
    isStreaming = true;
    scrollToBottom();

    // Add placeholder assistant message
    const assistantIdx = messages.length;
    messages = [...messages, { role: 'assistant', content: '' }];
    let fullContent = '';

    try {
      if (thinkMode) {
        // Think mode: use /v1/think via SSE proxy
        const resp = await fetch('/api/rag', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question,
            session_id: `widget-${Date.now()}`,
            user_id: 'widget-user',
            use_think: true,
          }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        fullContent = data.answer || 'No answer returned.';

        messages[assistantIdx] = {
          role: 'assistant',
          content: fullContent,
          queryType: data.query_type,
          memoriesRecalled: data.memories_recalled,
          toolsUsed: data.tools_used,
          traceId: data.trace_id,
        };
      } else {
        // Streaming mode: use /v1/query via SSE proxy
        const resp = await fetch('/api/rag', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question,
            use_think: false,
          }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const reader = resp.body?.getReader();
        if (!reader) throw new Error('No response body');

        const dec = new TextDecoder();
        let buffer = '';
        let sources: Source[] = [];
        let traceId = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += dec.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            try {
              const payload = JSON.parse(trimmed.slice(6));
              if (payload.chunk) {
                fullContent += payload.chunk;
                messages[assistantIdx] = { role: 'assistant', content: fullContent };
                scrollToBottom();
              }
              if (payload.done) {
                sources = payload.sources || [];
                traceId = payload.trace_id || '';
              }
            } catch {
              continue;
            }
          }
        }

        messages[assistantIdx] = {
          role: 'assistant',
          content: fullContent || 'No answer returned.',
          sources,
          traceId,
        };
      }
    } catch (err: any) {
      messages[assistantIdx] = {
        role: 'assistant',
        content: 'Something went wrong, try again.',
      };
    }

    isStreaming = false;
    messages = [...messages];
    scrollToBottom();
  }

  async function submitFeedback(msgIdx: number, rating: 'up' | 'down') {
    const msg = messages[msgIdx];
    if (!msg?.traceId || msg.feedbackGiven) return;

    try {
      await fetch('/api/rag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'feedback',
          trace_id: msg.traceId,
          rating: rating === 'up' ? 1 : -1,
        }),
      });
      messages[msgIdx].feedbackGiven = rating;
      messages = [...messages];
    } catch {
      // Silently fail feedback
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  let showSources: Record<number, boolean> = {};

  function toggleSources(idx: number) {
    showSources[idx] = !showSources[idx];
    showSources = { ...showSources };
  }
</script>

<div class="flex flex-col h-full max-h-[calc(100vh-4rem)] bg-gray-950 text-gray-100 rounded-xl overflow-hidden border border-gray-800">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-3 border-b border-gray-800">
    <h2 class="text-sm font-semibold text-gray-200">SynapseOS</h2>
    <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
      <span>Think</span>
      <input type="checkbox" bind:checked={thinkMode} class="accent-purple-500" />
      <span class="text-purple-400">{thinkMode ? 'ON' : 'OFF'}</span>
    </label>
  </div>

  <!-- Messages -->
  <div bind:this={chatContainer} class="flex-1 overflow-y-auto px-4 py-3 space-y-4">
    {#if messages.length === 0}
      <div class="flex items-center justify-center h-full text-gray-500 text-sm">
        Ask a question to query your knowledge base
      </div>
    {/if}

    {#each messages as msg, i}
      <div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
        <div class="max-w-[85%] {msg.role === 'user'
          ? 'bg-purple-600 text-white rounded-2xl rounded-br-sm px-4 py-2'
          : 'bg-gray-800 text-gray-100 rounded-2xl rounded-bl-sm px-4 py-3'}">
          <!-- Message content -->
          <div class="whitespace-pre-wrap text-sm leading-relaxed">
            {msg.content}
            {#if isStreaming && i === messages.length - 1 && msg.role === 'assistant'}
              <span class="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-1"></span>
            {/if}
          </div>

          <!-- Think mode metadata -->
          {#if msg.role === 'assistant' && msg.queryType}
            <div class="mt-2 flex flex-wrap gap-2 text-xs">
              <span class="bg-purple-900/50 text-purple-300 px-2 py-0.5 rounded-full">
                {msg.queryType}
              </span>
              {#if msg.memoriesRecalled}
                <span class="bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded-full">
                  {msg.memoriesRecalled} memories
                </span>
              {/if}
              {#if msg.toolsUsed?.length}
                <span class="bg-green-900/50 text-green-300 px-2 py-0.5 rounded-full">
                  tools: {msg.toolsUsed.join(', ')}
                </span>
              {/if}
            </div>
          {/if}

          <!-- Sources + Feedback (assistant only) -->
          {#if msg.role === 'assistant' && msg.sources?.length}
            <div class="mt-2 border-t border-gray-700 pt-2">
              <button
                on:click={() => toggleSources(i)}
                class="text-xs text-gray-400 hover:text-gray-200 transition"
              >
                {showSources[i] ? '▾ Hide sources' : '▸ Show sources'} ({msg.sources.length})
              </button>
              {#if showSources[i]}
                <div class="mt-1 space-y-1">
                  {#each msg.sources as src, si}
                    <div class="text-xs bg-gray-900 rounded p-2 text-gray-400">
                      <span class="text-gray-500">[{si + 1}]</span>
                      score: {src.score.toFixed(3)}
                      {#if src.source_url}
                        — <a href={src.source_url} target="_blank" class="text-purple-400 hover:underline truncate">{src.source_url}</a>
                      {/if}
                      <div class="mt-0.5 text-gray-500 truncate">{src.text.slice(0, 120)}…</div>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}

          <!-- Feedback buttons + Copy -->
          {#if msg.role === 'assistant' && !isStreaming && msg.content}
            <div class="mt-2 flex items-center gap-2">
              <button
                on:click={() => submitFeedback(i, 'up')}
                class="text-xs {msg.feedbackGiven === 'up' ? 'text-green-400' : 'text-gray-500 hover:text-green-400'} transition"
              >
                👍
              </button>
              <button
                on:click={() => submitFeedback(i, 'down')}
                class="text-xs {msg.feedbackGiven === 'down' ? 'text-red-400' : 'text-gray-500 hover:text-red-400'} transition"
              >
                👎
              </button>
              <button
                on:click={() => copyToClipboard(msg.content)}
                class="text-xs text-gray-500 hover:text-gray-300 transition ml-auto"
              >
                📋 Copy
              </button>
            </div>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  <!-- Input -->
  <div class="border-t border-gray-800 px-4 py-3">
    <div class="flex gap-2">
      <textarea
        bind:value={input}
        on:keydown={handleKeydown}
        placeholder={isStreaming ? 'Waiting for response…' : 'Ask a question…'}
        disabled={isStreaming}
        rows="1"
        class="flex-1 bg-gray-800 text-gray-100 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 placeholder-gray-500 disabled:opacity-50"
      ></textarea>
      <button
        on:click={sendMessage}
        disabled={isStreaming || !input.trim()}
        class="bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition"
      >
        Send
      </button>
    </div>
  </div>
</div>
