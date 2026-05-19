import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const listWorkspaceTeams = vi.hoisted(() => vi.fn())
const listWorkspaceSetups = vi.hoisted(() => vi.fn())
const listCaoToolDescriptors = vi.hoisted(() => vi.fn())
const getWorkspaceProviderRoleAccessSchema = vi.hoisted(() => vi.fn())
const upsertWorkspaceTeam = vi.hoisted(() => vi.fn())
const showSnackbar = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    listWorkspaceTeams,
    listWorkspaceSetups,
    listCaoToolDescriptors,
    getWorkspaceProviderRoleAccessSchema,
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
        roles: {
          member: {
            display_name: 'Member',
            cao_tools: ['send_message', 'handoff'],
            mcp_servers: {},
            providers: {},
            deletable: false,
          },
        },
        role_assignments: { aria: 'member' },
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
    listCaoToolDescriptors.mockResolvedValue([
      { name: 'send_message', description: 'Send a message' },
      { name: 'assign', description: 'Assign work' },
    ])
    getWorkspaceProviderRoleAccessSchema.mockResolvedValue({
      provider: 'linear',
      tools: [{ name: 'cao_linear.list_teams', description: 'List Linear teams' }],
      fields: {},
    })
    upsertWorkspaceTeam.mockResolvedValue({
      id: 'research',
      display_name: 'Research',
      workspace_setup: 'linear_delivery_setup',
      roles: {},
      role_assignments: {},
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
        roles: {},
        role_assignments: {},
        members: [],
        diagnostics: [],
      }),
    )
  })

  it('authors provider role fields from backend schema descriptors', async () => {
    listWorkspaceTeams.mockResolvedValue([
      {
        id: 'cao_delivery',
        display_name: 'CAO Delivery',
        workspace_setup: 'linear_delivery_setup',
        roles: {
          member: {
            display_name: 'Member',
            cao_tools: ['send_message', 'handoff'],
            mcp_servers: {},
            providers: {},
            deletable: false,
          },
        },
        role_assignments: {},
        members: ['aria'],
        diagnostics: [],
      },
    ])
    listWorkspaceSetups.mockResolvedValue([
      {
        id: 'linear_delivery_setup',
        display_name: 'Linear Delivery Setup',
        providers: ['linear'],
      },
    ])
    listCaoToolDescriptors.mockResolvedValue([
      { name: 'send_message', description: 'Send a message' },
      { name: 'handoff', description: 'Hand off work' },
    ])
    getWorkspaceProviderRoleAccessSchema.mockResolvedValue({
      provider: 'linear',
      tools: [{ name: 'cao_linear.get_issue', description: 'Read issue' }],
      fields: {
        tools: { type: 'string_list', required: true },
        issues: { type: 'string_list', required_for: ['cao_linear.get_issue'] },
        allow_top_level_create: { type: 'boolean' },
        reason: { type: 'string' },
      },
    })
    upsertWorkspaceTeam.mockResolvedValue({
      id: 'cao_delivery',
      display_name: 'CAO Delivery',
      workspace_setup: 'linear_delivery_setup',
      roles: {},
      role_assignments: {},
      members: [],
      diagnostics: [],
    })
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    render(<WorkspaceTeamsPanel />)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    fireEvent.click(screen.getByRole('button', { name: /add role/i }))
    await screen.findAllByRole('checkbox', { name: 'cao_linear.get_issue' })
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'cao_linear.get_issue' })[1])
    fireEvent.change(screen.getByLabelText('role_2 linear issues'), {
      target: { value: 'LIN-123\nLIN-456' },
    })
    fireEvent.click(screen.getByLabelText('role_2 linear allow_top_level_create'))
    fireEvent.change(screen.getByLabelText('role_2 linear reason'), {
      target: { value: 'verification' },
    })
    fireEvent.change(screen.getByLabelText('team role assignments'), {
      target: { value: JSON.stringify({ aria: 'role_2' }) },
    })
    fireEvent.click(screen.getByRole('button', { name: /save team/i }))

    await waitFor(() =>
      expect(upsertWorkspaceTeam).toHaveBeenCalledWith(
        expect.objectContaining({
          roles: expect.objectContaining({
            role_2: expect.objectContaining({
              providers: {
                linear: {
                  default: {
                    tools: ['cao_linear.get_issue'],
                    issues: ['LIN-123', 'LIN-456'],
                    allow_top_level_create: true,
                    reason: 'verification',
                  },
                },
              },
            }),
          }),
          role_assignments: { aria: 'role_2' },
        }),
      ),
    )
  })
})
