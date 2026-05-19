import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OutputViewer } from '../components/OutputViewer'
import { api } from '../api'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    api: {
      ...actual.api,
      getTerminalOutput: vi.fn(),
    },
  }
})

describe('OutputViewer', () => {
  beforeEach(() => {
    vi.mocked(api.getTerminalOutput).mockResolvedValue({
      output: 'hello from terminal',
      mode: 'last',
    })
  })

  it('labels terminal transcript access as an operator surface', async () => {
    render(<OutputViewer terminalId="term-1" onClose={() => {}} />)

    expect(screen.getByText('Operator Terminal Output')).toBeInTheDocument()
    expect(await screen.findByText('hello from terminal')).toBeInTheDocument()
  })
})
