# SynapseOS — SvelteKit Integration Guide

## 5 Steps to Add RAGChatWidget to Any SvelteKit Project

### Step 1: Install the TypeScript SDK

```bash
cd your-sveltekit-project
npm install @synapseos/sdk
# Or link locally if developing:
# npm link /path/to/synapseos/sdk/typescript
```

### Step 2: Add Environment Variables

Create or update `.env` in your SvelteKit project root:

```env
# These are read server-side only (never exposed to browser)
SYNAPSE_URL=https://your-synapseos-api.com
SYNAPSE_KEY=sk-syn-your-api-key

# These are read client-side (VITE_ prefix)
VITE_SYNAPSE_URL=https://your-synapseos-api.com
VITE_SYNAPSE_KEY=sk-syn-your-api-key
VITE_TENANT_ID=your-org-id
```

### Step 3: Copy Widget Files

Copy these files from the SynapseOS repo into your SvelteKit project:

```
widget/src/lib/components/RAGChatWidget.svelte → src/lib/components/RAGChatWidget.svelte
widget/src/routes/api/rag/+server.ts → src/routes/api/rag/+server.ts
widget/src/lib/synapseos.ts → src/lib/synapseos.ts
```

### Step 4: Add to a Page

In any `+page.svelte` where you want the chat widget:

```svelte
<script>
  import RAGChatWidget from '$lib/components/RAGChatWidget.svelte';
</script>

<div class="max-w-3xl mx-auto h-screen p-4">
  <RAGChatWidget />
</div>
```

### Step 5: Test

```bash
npm run dev
# Open http://localhost:5173
# Type a question and verify:
# - Streaming tokens appear in real time
# - Sources section is collapsible under each answer
# - Thumbs up/down submits feedback
# - Think mode toggle shows query_type badge
```

## Troubleshooting

- **"VITE_SYNAPSE_URL is not set"**: Add the env var to `.env` and restart dev server
- **CORS errors**: The SSE proxy at `/api/rag` handles CORS — make sure it's deployed
- **No streaming**: Check that `SYNAPSE_URL` points to a running SynapseOS instance
- **API key exposed**: Server-side env vars (`SYNAPSE_KEY`) are never sent to the browser
