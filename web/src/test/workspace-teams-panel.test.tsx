import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const listWorkspaceTeams = vi.hoisted(() => vi.fn())
const listWorkspaceSetups = vi.hoisted(() => vi.fn())
const upsertWorkspaceTeam = vi.hoisted(() => vi.fn())
const showSnackbar = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    listWorkspaceTeams,
    listWorkspaceSetups,
    upsertWorkspaceTeam,
  },
}))

vi.mock('../store', () => ({
  useStore: () => ({ showSnackbar }),
}))

describe('WorkspaceTeamsPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders teams, members, setup choices, and saves through the team owner API', async () => {
    listWorkspaceTeams.mockResolvedValue([
      {
        id: 'cao_delivery',
        display_name: 'CAO Delivery',
        workspace_setup: 'linear_delivery_setup',
        members: ['aria'],
        diagnostics: [
          'Workspace team cao_delivery pruned linear app_user_id U1 for out-of-team agent discovery',
          'Workspace team cao_delivery setup linear_delivery_setup requires unavailable provider linear',
        ],
      },
    ])
    listWorkspaceSetups.mockResolvedValue([
      {
        id: 'linear_delivery_setup',
        display_name: 'Linear Delivery Setup',
        providers: ['linear'],
      },
    ])
    upsertWorkspaceTeam.mockResolvedValue({
      id: 'research',
      display_name: 'Research',
      workspace_setup: 'linear_delivery_setup',
      members: [],
      diagnostics: [],
    })
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    render(<WorkspaceTeamsPanel />)

    expect(await screen.findByText('CAO Delivery')).toBeInTheDocument()
    expect(screen.getByText('aria')).toBeInTheDocument()
    expect(screen.queryByText(/pruned linear/)).not.toBeInTheDocument()
    expect(screen.getByText(/requires unavailable provider linear/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('team id'), { target: { value: 'research' } })
    fireEvent.change(screen.getByLabelText('team display name'), {
      target: { value: 'Research' },
    })
    fireEvent.change(screen.getByLabelText('team workspace setup'), {
      target: { value: 'linear_delivery_setup' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save team/i }))

    await waitFor(() =>
      expect(upsertWorkspaceTeam).toHaveBeenCalledWith({
        id: 'research',
        display_name: 'Research',
        workspace_setup: 'linear_delivery_setup',
        members: [],
        diagnostics: [],
      }),
    )
  })
})
