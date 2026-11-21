// Fulcra for Hermes Desktop: proof-of-concept Agents I Know page.
// Plain ESM loaded uncompiled by Desktop: no JSX, and only @hermes/plugin-sdk and react imports.
import {
  Button,
  host,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  StatusDot,
  TRANSCRIPT_DIRECTIVE_AREA
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/fulcra'

// What the backend's /ping answers mean for the user.
const STATES = {
  connected: { tone: 'success', text: 'Connected to Fulcra.' },
  not_configured: {
    tone: 'warning',
    text: 'The Fulcra MCP server isn\u2019t added yet. Run /fulcra setup in a chat, then sign in to fulcra under MCP servers.'
  },
  not_connected: {
    tone: 'warning',
    text: 'Fulcra isn\u2019t connected in this session yet. Start a chat, then try again. If it still fails, sign in to fulcra under MCP servers.'
  },
  error: { tone: 'error', text: 'Fulcra answered with an error.' }
}

function AgentsIKnowPage({ ctx }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const ping = async () => {
    setBusy(true)
    try {
      setResult(await ctx.rest('/ping', { method: 'POST', timeoutMs: 30000 }))
    } catch (error) {
      setResult({ state: 'error', detail: String((error && error.message) || error) })
    } finally {
      setBusy(false)
    }
  }

  const state = result && (STATES[result.state] || STATES.error)
  return jsxs('div', {
    className: 'flex h-full flex-col gap-4 p-6 text-sm',
    children: [
      jsx('div', { className: 'text-lg font-medium', children: 'Agents I Know' }),
      jsx('div', {
        className: 'text-(--ui-text-tertiary)',
        children: 'Proof of concept: this page calls the Fulcra MCP server through the plugin\u2019s backend.'
      }),
      jsx('div', {
        children: jsx(Button, { onClick: ping, disabled: busy, children: busy ? 'Pinging\u2026' : 'Ping Fulcra' })
      }),
      state &&
        jsxs('div', {
          className: 'flex items-start gap-2',
          children: [
            jsx(StatusDot, { tone: state.tone }),
            jsxs('div', {
              className: 'flex flex-col gap-1',
              children: [
                jsx('div', { children: state.text }),
                result.seconds != null && jsx('div', {
                  className: 'text-(--ui-text-tertiary)',
                  children: `Tool: ${result.tool}, ${result.seconds} s`
                }),
                result.detail && jsx('div', { className: 'text-(--ui-text-tertiary)', children: result.detail })
              ]
            })
          ]
        })
    ]
  })
}

// The model can offer the page with a paragraph that is exactly ::fulcra-agents-i-know
function OpenCard() {
  return jsx(Button, {
    variant: 'outline',
    onClick: () => host.navigate(PATH),
    children: 'Open Agents I Know'
  })
}

export default {
  id: 'fulcra',
  name: 'Fulcra',
  register(ctx) {
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(AgentsIKnowPage, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Agents I Know', codicon: 'organization' } }
    ])
    if (typeof TRANSCRIPT_DIRECTIVE_AREA === 'string') {
      ctx.register({
        id: 'open-card',
        area: TRANSCRIPT_DIRECTIVE_AREA,
        data: { name: 'fulcra-agents-i-know', render: () => jsx(OpenCard, {}) }
      })
    }
  }
}
