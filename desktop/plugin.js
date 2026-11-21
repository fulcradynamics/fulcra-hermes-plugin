// Fulcra for Hermes Desktop: the Agents I Know page (connection and a ping for now; contacts come later).
// Plain ESM loaded uncompiled by Desktop: no JSX, and only @hermes/plugin-sdk and react imports.
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
const POLL_MS = 2000
const SIGN_IN_MS = 5 * 60 * 1000

const message = error => String((error && error.message) || error || 'Unknown error')
const muted = children => jsx('div', { className: 'text-(--ui-text-tertiary)', children })

// StatusDot tones: good | muted | warn | bad.
// The Fulcra server's row from Hermes's own MCP status (cached; never connects or signs in).
async function serverStatus(name) {
  const result = await host.request('mcp.servers.status', {})
  return ((result && result.servers) || []).find(server => server.name === name) || null
}

function Line({ tone, children }) {
  return jsxs('div', {
    className: 'flex items-start gap-2',
    children: [jsx(StatusDot, { tone }), jsx('div', { className: 'flex flex-col gap-1', children })]
  })
}

function AgentsIKnowPage({ ctx }) {
  const [info, setInfo] = useState(null) // {server, url, default_url} from the plugin's backend
  const [runtime, setRuntime] = useState(null) // Hermes's MCP status row for the server
  const [step, setStep] = useState('idle') // idle | confirm | adding | signing-in | signed-in
  const [ping, setPing] = useState(null)
  const [error, setError] = useState(null)

  const refresh = async () => {
    try {
      const next = await ctx.rest('/status')
      setInfo(next)
      setRuntime(next.url ? await serverStatus(next.server).catch(() => null) : null)
      setError(null)
    } catch (e) {
      setError(message(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const add = async () => {
    setStep('adding')
    try {
      await ctx.rest('/connect', { method: 'POST', body: {} })
      await refresh()
      setStep('idle')
    } catch (e) {
      setError(message(e))
      setStep('idle')
    }
  }

  // Hermes's own MCP sign-in, as in Capabilities > MCP servers: the browser opens, the page polls.
  const signIn = async () => {
    setError(null)
    setStep('signing-in')
    try {
      const flow = await host.request('mcp.servers.oauth.start', { name: info.server })
      await ctx.os.openExternal(flow.auth_url)
      const deadline = Date.now() + SIGN_IN_MS
      const stop = ctx.setInterval(async () => {
        try {
          const poll = await host.request('mcp.servers.oauth.poll', { name: info.server, session_id: flow.session_id })
          if (poll.status === 'pending' && Date.now() < deadline) return
          stop()
          if (poll.status === 'approved') {
            setStep('signed-in')
            refresh()
          } else {
            setStep('idle')
            setError(poll.error || poll.message || 'Sign-in did not finish.')
            host.request('mcp.servers.oauth.cancel', { name: info.server, session_id: flow.session_id }).catch(() => {})
          }
        } catch (e) {
          stop()
          setStep('idle')
          setError(message(e))
        }
      }, POLL_MS)
    } catch (e) {
      setStep('idle')
      setError(message(e))
    }
  }

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

  if (info && !info.url) {
    children.push(
      jsx(Line, {
        tone: 'warn',
        children: [
          jsx('div', { children: 'Fulcra isn\u2019t added to Hermes yet.' }),
          step === 'confirm'
            ? muted(`Hermes will add the Fulcra MCP server (${info.default_url}) as \u201c${info.server}\u201d and offer its tools in new chats. You can remove it any time under Capabilities > MCP servers.`)
            : null
        ]
      }),
      step === 'confirm'
        ? jsxs('div', {
            className: 'flex gap-2',
            children: [
              jsx(Button, { onClick: add, children: 'Add Fulcra' }),
              jsx(Button, { variant: 'outline', onClick: () => setStep('idle'), children: 'Cancel' })
            ]
          })
        : jsx('div', {
            children: jsx(Button, {
              onClick: () => setStep('confirm'),
              disabled: step === 'adding',
              children: step === 'adding' ? 'Adding\u2026' : 'Connect Fulcra\u2026'
            })
          })
    )
  }

  if (info && info.url) {
    const live = runtime && runtime.connected
    const needsAuth = runtime && runtime.needs_auth
    children.push(
      jsx(Line, {
        tone: live ? 'good' : needsAuth ? 'warn' : 'muted',
        children: [
          jsx('div', {
            children: live
              ? `Connected to Fulcra (${runtime.tools} tools).`
              : needsAuth
                ? 'Fulcra is added; sign in to use it.'
                : step === 'signed-in'
                  ? 'Signed in. Start a new chat to use Fulcra.'
                  : 'Fulcra is added. Hermes connects to it when a chat starts.'
          }),
          muted(info.url)
        ]
      }),
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          !live &&
            jsx(Button, {
              onClick: signIn,
              disabled: step === 'signing-in',
              children: step === 'signing-in' ? 'Finish signing in in your browser\u2026' : 'Sign in to Fulcra'
            }),
          jsx(Button, {
            variant: 'outline',
            onClick: runPing,
            disabled: ping && ping.state === 'busy',
            children: ping && ping.state === 'busy' ? 'Pinging\u2026' : 'Ping Fulcra'
          })
        ]
      }),
      !live && muted('If Hermes runs on another computer, sign in from Capabilities > MCP servers instead.')
    )
  }

  if (ping && ping.state !== 'busy') {
    const text = {
      connected: `Fulcra answered in ${ping.seconds} s.`,
      not_configured: 'Fulcra isn\u2019t added to Hermes.',
      not_connected: 'Hermes hasn\u2019t connected to Fulcra in this window yet: start a chat, then try again.',
      error: 'Fulcra answered with an error. If you aren\u2019t signed in, sign in and try again.'
    }[ping.state] || 'Unexpected answer.'
    children.push(
      jsx(Line, {
        tone: ping.state === 'connected' ? 'good' : ping.state === 'error' ? 'bad' : 'warn',
        children: [jsx('div', { children: text }), ping.detail ? muted(ping.detail) : null]
      })
    )
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
