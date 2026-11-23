// Fulcra for Hermes Desktop: the Agents I Know page (connection status and a ping for now; contacts come later).
// Plain ESM loaded uncompiled by Desktop: no JSX, and only @hermes/plugin-sdk and react imports.
// The page never changes Hermes's config or signs in: it shows the Hermes commands still needed and points to
// Desktop's own Capabilities > MCP servers.
import {
  Button,
  host,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  StatusDot,
  TRANSCRIPT_DIRECTIVE_AREA
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/fulcra'

const message = error => String((error && error.message) || error || 'Unknown error')
const muted = children => jsx('div', { className: 'text-(--ui-text-tertiary)', children })

// StatusDot tones: good | muted | warn | bad.
function Line({ tone, children }) {
  return jsxs('div', {
    className: 'flex items-start gap-2',
    // The dot sits in a box one text line tall, so it centers on the first line.
    children: [
      jsx('span', { className: 'flex h-5 shrink-0 items-center', children: jsx(StatusDot, { tone }) }),
      jsx('div', { className: 'flex flex-col gap-1', children })
    ]
  })
}

function Command({ ctx, purpose, command }) {
  const [copied, setCopied] = useState(false)
  return jsxs('div', {
    className: 'flex flex-col gap-1',
    children: [
      jsx('div', { children: purpose }),
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('code', { className: 'select-all rounded bg-(--ui-bg-quaternary) px-2 py-1 font-mono text-xs', children: command }),
          jsx(Button, {
            variant: 'ghost',
            onClick: async () => setCopied(await ctx.os.writeClipboard(command)),
            children: copied ? 'Copied' : 'Copy'
          })
        ]
      })
    ]
  })
}

const PING = {
  connected: ['good', s => `Fulcra answered in ${s.seconds} s.`],
  not_configured: ['warn', () => 'Fulcra isn\u2019t added to Hermes.'],
  not_allowed: ['warn', () => 'The Fulcra plugin may not use the fulcra server yet.'],
  not_connected: [
    'warn',
    () =>
      'Hermes hasn\u2019t connected to Fulcra here yet. If you haven\u2019t signed in, sign in under Capabilities > MCP servers; otherwise start a chat, then try again.'
  ],
  error: ['bad', () => 'Fulcra answered with an error. You may need to sign in again under Capabilities > MCP servers.']
}

function AgentsIKnowPage({ ctx }) {
  const [info, setInfo] = useState(null) // {server, url, allowed, commands} from the plugin's backend
  const [ping, setPing] = useState(null)
  const [error, setError] = useState(null)

  const refresh = async () => {
    try {
      setInfo(await ctx.rest('/status'))
      setError(null)
    } catch (e) {
      setError(message(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const runPing = async () => {
    setPing({ state: 'busy' })
    try {
      setPing(await ctx.rest('/ping', { method: 'POST', timeoutMs: 30000 }))
    } catch (e) {
      setPing({ state: 'error', detail: message(e) })
    }
  }

  const children = [
    jsx('div', { className: 'text-lg font-medium', children: 'Agents I Know' }),
    muted('Fulcra connects your agent with other people\u2019s agents. Your contacts will show here; for now, ask in a chat (\u201cshow my Fulcra agent contacts\u201d).')
  ]

  if (!info && !error) children.push(muted('Loading\u2026'))

  if (info) {
    const ready = info.url && info.allowed
    children.push(
      jsx(Line, {
        tone: ready ? 'good' : 'warn',
        children: [
          jsx('div', {
            children: !info.url
              ? 'Fulcra isn\u2019t added to Hermes yet.'
              : info.allowed
                ? 'Fulcra is added to Hermes.'
                : 'Fulcra is added, but this page and what\u2019s new may not use it yet.'
          }),
          info.url ? muted(info.url) : null
        ]
      })
    )
    if (info.commands.length) {
      children.push(
        muted('Run in a terminal on the machine running Hermes (or ask Hermes to run them for you):'),
        ...info.commands.map(c => jsx(Command, { ctx, purpose: c.purpose, command: c.command })),
        muted(
          'You can also add the server and sign in under Capabilities > MCP servers. After signing in, start a new chat; a running Hermes may need a restart to pick up the sign-in.'
        )
      )
    }
    children.push(
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          ready &&
            jsx(Button, {
              variant: 'outline',
              onClick: runPing,
              disabled: ping && ping.state === 'busy',
              children: ping && ping.state === 'busy' ? 'Pinging\u2026' : 'Ping Fulcra'
            }),
          jsx(Button, { variant: 'ghost', onClick: refresh, children: 'Refresh' })
        ]
      })
    )
  }

  if (ping && ping.state !== 'busy') {
    const [tone, text] = PING[ping.state] || PING.error
    children.push(jsx(Line, { tone, children: [jsx('div', { children: text(ping) }), ping.detail ? muted(ping.detail) : null] }))
  }

  if (error) children.push(jsx(Line, { tone: 'bad', children: jsx('div', { children: error }) }))

  return jsx('div', { className: 'flex h-full max-w-2xl flex-col gap-4 p-6 text-sm', children })
}

// The model can offer the page with a paragraph that is exactly ::fulcra-agents-i-know (see the agents-i-know skill).
function OpenCard() {
  return jsx(Button, { variant: 'outline', onClick: () => host.navigate(PATH), children: 'Open Agents I Know' })
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
