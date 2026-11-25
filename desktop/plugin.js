// Fulcra for Hermes Desktop: the Agents I Know page.
// Plain ESM loaded uncompiled by Desktop: no JSX, and only @hermes/plugin-sdk and react imports.
// The page never changes Hermes's config or signs in: until Fulcra is added and answering, it shows the Hermes
// commands still needed and points to Desktop's own Capabilities > Connectors. Then it runs the Agents I Know
// app the Fulcra MCP server offers MCP Apps hosts (shipped as desktop/agents-i-know.html) in a sandboxed frame,
// acting as its host: tool calls go to the plugin's backend, which makes them with Hermes's MCP client.
import { Button, host, ROUTES_AREA, SandboxedFrame, SIDEBAR_NAV_AREA, StatusDot, TRANSCRIPT_DIRECTIVE_AREA, useTheme } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/fulcra'
const API_VERSION = 2 // dashboard/plugin_api.py's

const message = error => String((error && error.message) || error || 'Unknown error')
const muted = children => jsx('div', { className: 'text-(--ui-text-tertiary)', children })
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

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

const NOT_READY = {
  not_allowed: ['warn', 'The Fulcra plugin may not use the fulcra server yet.'],
  not_connected: [
    'warn',
    'Hermes connects to Fulcra when a chat starts. Start a chat, then try again. If you haven\u2019t signed in, sign in under Capabilities > Connectors.'
  ],
  error: ['bad', 'Fulcra answered with an error. You may need to sign in again under Capabilities > MCP servers.']
}

function AgentsIKnowPage({ ctx }) {
  const [info, setInfo] = useState(null) // {server, url, allowed, commands} from the plugin's backend
  const [probe, setProbe] = useState(null) // {state, detail?}: whether Fulcra answers here
  const [error, setError] = useState(null)

  // A call to a server Hermes hasn't connected counts against its circuit breaker (three in a row pause the
  // server for a minute), so the page checks once before the app makes its calls, then on request.
  const check = async () => {
    setProbe({ state: 'busy' })
    try {
      setProbe(await ctx.rest('/ping', { method: 'POST', timeoutMs: 40000 }))
    } catch (e) {
      setProbe({ state: 'error', detail: message(e) })
    }
  }

  const refresh = async () => {
    try {
      const status = await ctx.rest('/status')
      if (status.api !== API_VERSION) {
        // Hermes keeps an earlier version's backend running after the plugin is reinstalled or updated.
        return setError('Restart Hermes to finish installing this version of the Fulcra plugin.')
      }
      setInfo(status)
      setError(null)
      if (status.url && status.allowed) check()
    } catch (e) {
      setError(message(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  if (probe && probe.state === 'connected') return jsx(AgentsApp, { ctx })

  const children = [jsx('div', { className: 'text-lg font-medium', children: 'Agents I Know' })]

  if (error) children.push(jsx(Line, { tone: 'bad', children: jsx('div', { children: error }) }))
  else if (!info || (probe && probe.state === 'busy')) children.push(muted('Loading\u2026'))
  else if (info.commands.length) {
    children.push(
      muted('Fulcra connects your agent with other people\u2019s agents. Your contacts show here once Fulcra is set up.'),
      jsx(Line, {
        tone: 'warn',
        children: [
          jsx('div', {
            children: info.url ? 'Fulcra is added, but this page and what\u2019s new may not use it yet.' : 'Fulcra isn\u2019t added to Hermes yet.'
          }),
          info.url ? muted(info.url) : null
        ]
      }),
      muted('Run in a terminal on the machine running Hermes:'),
      ...info.commands.map(c => jsx(Command, { ctx, purpose: c.purpose, command: c.command })),
      muted(
        'You can also add it under Capabilities > Connectors > Add your own: name fulcra, Streamable HTTP, this URL, OAuth; then sign in. After signing in, start a new chat; a running Hermes may need a restart to pick up the sign-in.'
      ),
      jsx(Button, { variant: 'outline', className: 'self-start', onClick: refresh, children: 'Check again' })
    )
  } else if (probe) {
    const [tone, text] = NOT_READY[probe.state] || NOT_READY.error
    children.push(
      jsx(Line, { tone, children: [jsx('div', { children: text }), probe.detail ? muted(probe.detail) : null] }),
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          probe.state === 'not_connected' && jsx(Button, { variant: 'outline', onClick: () => host.newChat(), children: 'Start a chat' }),
          jsx(Button, { variant: 'ghost', onClick: check, children: 'Try again' })
        ]
      })
    )
  }

  return jsx('div', { className: 'flex h-full max-w-2xl flex-col gap-4 p-6 text-sm', children })
}

// The MCP Apps host side (SEP-1865) of the app in the frame: JSON-RPC over postMessage.
const PROTOCOL_VERSION = '2026-01-26'
let appUrl // The app as a data: URL, the one kind of document SandboxedFrame embeds besides web pages.

async function loadApp(ctx) {
  if (!appUrl) {
    const bytes = new TextEncoder().encode((await ctx.rest('/app', { timeoutMs: 30000 })).html)
    let binary = ''
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
    appUrl = 'data:text/html;base64,' + btoa(binary)
  }
  return appUrl
}

const textOf = content => (content || []).filter(c => c.type === 'text').map(c => c.text).join('\n\n')

// The app's "Continue in Hermes": a new chat, with what the app gave as model context after the request.
async function sendToChat(text) {
  host.newChat()
  for (let i = 0; i < 20; i++) {
    if (host.composer.submit('new', text)) return true
    await sleep(150) // The new chat's composer mounts after navigation.
  }
  return false
}

function AgentsApp({ ctx }) {
  const frame = useRef(null)
  const [src, setSrc] = useState(appUrl)
  const [error, setError] = useState(null)
  const { resolvedMode } = useTheme()
  const mode = useRef(resolvedMode)
  mode.current = resolvedMode

  useEffect(() => {
    loadApp(ctx).then(setSrc, e => setError(message(e)))
  }, [])

  useEffect(() => {
    let context = '' // ui/update-model-context replaces it; an empty one clears it.
    const post = data => frame.current?.contentWindow?.postMessage({ jsonrpc: '2.0', ...data }, '*')
    const methods = {
      'ui/initialize': () => ({
        protocolVersion: PROTOCOL_VERSION,
        hostInfo: { name: 'Hermes', version: '1' },
        hostCapabilities: { openLinks: {}, serverTools: {}, message: { text: {} }, updateModelContext: { text: {} } },
        hostContext: { theme: mode.current, displayMode: 'fullscreen', availableDisplayModes: ['fullscreen'], platform: 'desktop' }
      }),
      'tools/call': ({ name, arguments: args }) => ctx.rest('/call', { method: 'POST', body: { name, arguments: args || {} }, timeoutMs: 70000 }),
      'ui/open-link': async ({ url }) => ((await ctx.os.openExternal(url)) ? {} : { isError: true }),
      'ui/update-model-context': ({ content }) => {
        context = textOf(content)
        return {}
      },
      'ui/message': async ({ content }) => {
        const text = [textOf(content), context && `Context from Agents I Know:\n${context}`].filter(Boolean).join('\n\n')
        return (await sendToChat(text)) ? {} : { isError: true }
      },
      'ui/request-display-mode': () => ({ mode: 'fullscreen' }),
      ping: () => ({})
    }
    const onMessage = async ({ source, data }) => {
      if (!frame.current || source !== frame.current.contentWindow || !data || data.jsonrpc !== '2.0') return
      if (data.id === undefined || !data.method) return // Notifications (initialized, size-changed) need nothing.
      const method = methods[data.method]
      if (!method) return post({ id: data.id, error: { code: -32601, message: `Hermes doesn't support ${data.method}` } })
      try {
        post({ id: data.id, result: await method(data.params || {}) })
      } catch (e) {
        post({ id: data.id, error: { code: -32603, message: message(e) } })
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme: resolvedMode } },
      '*'
    )
  }, [resolvedMode])

  if (error) return jsx('div', { className: 'p-6 text-sm', children: jsx(Line, { tone: 'bad', children: jsx('div', { children: error }) }) })
  if (!src) return jsx('div', { className: 'p-6 text-sm', children: muted('Loading\u2026') })
  return jsx(SandboxedFrame, { ref: frame, src, title: 'Agents I Know', sandbox: 'allow-scripts allow-forms', className: 'h-full w-full' })
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
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Agents I Know', codicon: 'comment-discussion' } }
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
