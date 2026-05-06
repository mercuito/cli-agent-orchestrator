import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { TerminalView } from '../components/TerminalView'

const terminalInstance = vi.hoisted(() => ({
  loadAddon: vi.fn(),
  open: vi.fn(),
  write: vi.fn(),
  dispose: vi.fn(),
  onData: vi.fn(),
  onSelectionChange: vi.fn(),
  getSelection: vi.fn(() => ''),
  attachCustomKeyEventHandler: vi.fn(),
  focus: vi.fn(),
  rows: 24,
  cols: 80,
}))

const fitAddonInstance = vi.hoisted(() => ({
  fit: vi.fn(),
}))

vi.mock('@xterm/xterm', () => ({
  Terminal: vi.fn(() => terminalInstance),
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(() => fitAddonInstance),
}))

describe('TerminalView', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    terminalInstance.onData.mockReset()
    terminalInstance.onSelectionChange.mockReset()
    terminalInstance.attachCustomKeyEventHandler.mockReset()
    terminalInstance.focus.mockReset()
    fitAddonInstance.fit.mockReset()
  })

  it('includes a signed terminal token in the websocket URL when provided', () => {
    const close = vi.fn()
    const sockets: MockWebSocket[] = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      binaryType = ''
      readyState = MockWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: (() => void) | null = null
      send = vi.fn()
      close = vi.fn()

      constructor(public url: string) {
        sockets.push(this)
      }
    }

    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal('location', { protocol: 'https:', host: 'macmini.bagrid-halfbeak.ts.net' })
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn()
        disconnect = vi.fn()
      },
    )
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.stubGlobal('navigator', {
      clipboard: {
        writeText: vi.fn(() => Promise.resolve()),
      },
    })

    render(
      <TerminalView
        terminalId="term-1"
        provider="codex"
        agentProfile="developer"
        terminalToken="signed token/with spaces"
        onClose={close}
      />,
    )

    expect(sockets).toHaveLength(1)
    expect(sockets[0].url).toBe(
      'wss://macmini.bagrid-halfbeak.ts.net/terminals/term-1/ws?terminal_token=signed%20token%2Fwith%20spaces',
    )
  })
})
