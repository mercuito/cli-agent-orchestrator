import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const listWorkspaceTeams = vi.hoisted(() => vi.fn())
const listWorkspaceSetups = vi.hoisted(() => vi.fn())
const listCaoToolDescriptors = vi.hoisted(() => vi.fn())
const getWorkspaceToolProviderRoleAccessSchema = vi.hoisted(() => vi.fn())
const listAgents = vi.hoisted(() => vi.fn())
const createWorkspaceTeam = vi.hoisted(() => vi.fn())
const updateWorkspaceTeamMetadata = vi.hoisted(() => vi.fn())
const putWorkspaceTeamRole = vi.hoisted(() => vi.fn())
const deleteWorkspaceTeamRole = vi.hoisted(() => vi.fn())
const putWorkspaceTeamMember = vi.hoisted(() => vi.fn())
const deleteWorkspaceTeamMember = vi.hoisted(() => vi.fn())
const showSnackbar = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    listWorkspaceTeams,
    listWorkspaceSetups,
    listCaoToolDescriptors,
    getWorkspaceToolProviderRoleAccessSchema,
    listAgents,
    createWorkspaceTeam,
    updateWorkspaceTeamMetadata,
    putWorkspaceTeamRole,
    deleteWorkspaceTeamRole,
    putWorkspaceTeamMember,
    deleteWorkspaceTeamMember,
  },
}))

vi.mock('../store', () => ({
  useStore: () => ({ showSnackbar }),
}))

const memberRole = {
  display_name: 'Member',
  cao_tools: ['read_inbox_message'],
  mcp_servers: {},
  providers: {},
  deletable: false,
}

const reviewerRole = {
  display_name: 'Reviewer',
  cao_tools: ['read_inbox_message'],
  mcp_servers: { shell: { command: 'shell' } },
  providers: { linear: { default: { tools: ['cao_linear.get_issue'] } } },
  deletable: true,
}

function team(overrides = {}) {
  return {
    id: 'safari_review_team',
    display_name: 'Safari Review Team',
    workspace_setup: 'linear_delivery_setup',
    roles: {
      member: memberRole,
      reviewer: reviewerRole,
    },
    role_assignments: { code_reviewer: 'reviewer' },
    members: ['code_reviewer'],
    member_details: [
      {
        agent_id: 'code_reviewer',
        display_name: 'Code Reviewer',
        role_id: 'reviewer',
        role_explicitly_assigned: true,
      },
    ],
    diagnostics: [
      'Workspace team safari_review_team pruned linear app_user_id U1 for out-of-team agent discovery',
      'Workspace team safari_review_team setup linear_delivery_setup requires unavailable provider linear',
    ],
    ...overrides,
  }
}

const agents = [
  {
    agent_id: 'code_reviewer',
    display_name: 'Code Reviewer',
    cli_provider: 'codex',
    config: { id: 'code_reviewer', display_name: 'Code Reviewer', mcp_servers: { shell: { command: 'shell' } } },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
  },
  {
    agent_id: 'technical_writer',
    display_name: 'Technical Writer',
    cli_provider: 'claude_code',
    config: { id: 'technical_writer', display_name: 'Technical Writer', mcp_servers: { files: { command: 'files' } } },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
  },
  {
    agent_id: 'qa_analyst',
    display_name: 'QA Analyst',
    cli_provider: 'codex',
    config: { id: 'qa_analyst', display_name: 'QA Analyst', mcp_servers: {} },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
  },
]

function seedDashboard(initialTeams = [team()]) {
  listWorkspaceTeams.mockResolvedValue(initialTeams)
  listWorkspaceSetups.mockResolvedValue([
    {
      id: 'linear_delivery_setup',
      display_name: 'Linear Delivery Setup',
      providers: ['linear'],
    },
    {
      id: 'docs_setup',
      display_name: 'Docs Setup',
      providers: [],
    },
  ])
  listCaoToolDescriptors.mockResolvedValue([
    { name: 'read_inbox_message', description: 'Read inbox message' },
    { name: 'send_message', description: 'Send message' },
  ])
  getWorkspaceToolProviderRoleAccessSchema.mockResolvedValue({
    provider: 'linear',
    tools: [
      { name: 'cao_linear.get_issue', description: 'Read Linear issue' },
      { name: 'cao_linear.create_comment', description: 'Create Linear comment' },
    ],
    fields: {
      tools: { type: 'string_list' },
      issues: { type: 'string_list' },
      allow_top_level_create: { type: 'boolean' },
      reason: { type: 'string' },
    },
  })
  listAgents.mockResolvedValue(agents)
}

describe('WorkspaceTeamsPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders the mockup-shaped team editor and uses granular member and metadata endpoints', async () => {
    // Given
    seedDashboard()
    putWorkspaceTeamMember
      .mockResolvedValueOnce(team({
        members: ['code_reviewer', 'technical_writer'],
        member_details: [
          { agent_id: 'code_reviewer', display_name: 'Code Reviewer', role_id: 'reviewer', role_explicitly_assigned: true },
          { agent_id: 'technical_writer', display_name: 'Technical Writer', role_id: 'member', role_explicitly_assigned: false },
        ],
      }))
      .mockResolvedValueOnce(team({
        role_assignments: { code_reviewer: 'member', technical_writer: 'member' },
        members: ['code_reviewer', 'technical_writer'],
        member_details: [
          { agent_id: 'code_reviewer', display_name: 'Code Reviewer', role_id: 'member', role_explicitly_assigned: true },
          { agent_id: 'technical_writer', display_name: 'Technical Writer', role_id: 'member', role_explicitly_assigned: false },
        ],
      }))
    deleteWorkspaceTeamMember.mockResolvedValue(team({
      members: ['code_reviewer'],
      member_details: [
        { agent_id: 'code_reviewer', display_name: 'Code Reviewer', role_id: 'member', role_explicitly_assigned: true },
      ],
    }))
    updateWorkspaceTeamMetadata.mockResolvedValue(team({
      display_name: 'Safari Review Guild',
      workspace_setup: 'docs_setup',
    }))
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)

    // Then
    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /new team/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Available agents' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Roles' })).toBeInTheDocument()
    expect(screen.getByText('safari_review_team')).toBeInTheDocument()
    expect(await screen.findByText('Technical Writer')).toBeInTheDocument()
    expect(screen.queryByLabelText(/team role assignments/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/allow_top_level_create/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/reason/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/pruned linear/)).not.toBeInTheDocument()
    expect(screen.getByText(/requires unavailable provider linear/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search available agents'), {
      target: { value: 'technical' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add Technical Writer' }))

    await waitFor(() => expect(putWorkspaceTeamMember).toHaveBeenCalledWith(
      'safari_review_team',
      'technical_writer',
      {},
    ))
    expect(await screen.findByRole('button', { name: /Safari Review Team.*2 agents.*2 roles/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Code Reviewer role'), {
      target: { value: 'member' },
    })

    await waitFor(() => expect(putWorkspaceTeamMember).toHaveBeenCalledWith(
      'safari_review_team',
      'code_reviewer',
      { role_id: 'member' },
    ))

    fireEvent.change(screen.getByLabelText('Search members'), {
      target: { value: 'technical' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remove Technical Writer' }))

    await waitFor(() => expect(deleteWorkspaceTeamMember).toHaveBeenCalledWith('safari_review_team', 'technical_writer'))

    fireEvent.change(screen.getByLabelText('Team display name'), {
      target: { value: 'Safari Review Guild' },
    })
    fireEvent.blur(screen.getByLabelText('Team display name'))
    fireEvent.change(screen.getByLabelText('Workspace setup'), {
      target: { value: 'docs_setup' },
    })

    await waitFor(() => expect(updateWorkspaceTeamMetadata).toHaveBeenLastCalledWith(
      'safari_review_team',
      { display_name: 'Safari Review Guild', workspace_setup: 'docs_setup' },
    ))
  })

  it('creates, filters, saves, and deletes roles through the role drawer without provider-specific fields', async () => {
    // Given
    seedDashboard()
    putWorkspaceTeamRole
      .mockResolvedValueOnce(team({
        roles: {
          member: memberRole,
          reviewer: reviewerRole,
          role_3: { display_name: 'Role 3', cao_tools: [], mcp_servers: {}, providers: {}, deletable: true },
        },
      }))
      .mockResolvedValueOnce(team({
        roles: {
          member: memberRole,
          reviewer: reviewerRole,
          role_3: {
            display_name: 'Automation Reviewer',
            cao_tools: ['send_message'],
            mcp_servers: { files: { command: 'files' } },
            providers: { linear: { default: { tools: ['cao_linear.create_comment'] } } },
            deletable: true,
          },
        },
      }))
    deleteWorkspaceTeamRole.mockResolvedValue(team())
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: '+ New role' }))

    // Then
    await waitFor(() => expect(putWorkspaceTeamRole).toHaveBeenCalledWith(
      'safari_review_team',
      'role_3',
      { display_name: 'Role 3', cao_tools: [], mcp_servers: {}, providers: {}, deletable: true },
    ))
    expect(await screen.findByRole('complementary', { name: 'Edit role' })).toBeInTheDocument()
    expect(screen.queryByText('role_3')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close role editor' }))
    expect(screen.getByText('Select a role to edit its tools.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Role 3 0 members/ }))

    fireEvent.change(screen.getByLabelText('Role display name'), {
      target: { value: 'Automation Reviewer' },
    })
    fireEvent.change(screen.getByLabelText('Search tools'), {
      target: { value: 'comment' },
    })
    expect(screen.getByLabelText('Toggle cao_linear.create_comment')).toBeInTheDocument()
    expect(screen.queryByLabelText('Toggle send_message')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search tools'), { target: { value: '' } })
    expect(await screen.findByLabelText('Toggle files')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Toggle send_message'))
    fireEvent.click(screen.getByLabelText('Toggle files'))
    fireEvent.click(screen.getByLabelText('Toggle cao_linear.create_comment'))
    fireEvent.click(screen.getByRole('button', { name: 'Save role' }))

    await waitFor(() => expect(putWorkspaceTeamRole).toHaveBeenLastCalledWith(
      'safari_review_team',
      'role_3',
      {
        display_name: 'Automation Reviewer',
        cao_tools: ['send_message'],
        mcp_servers: { files: { command: 'files' } },
        providers: { linear: { default: { tools: ['cao_linear.create_comment'] } } },
        deletable: true,
      },
    ))

    fireEvent.click(screen.getByRole('button', { name: 'Delete role' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/0 members will fall back to member/i)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete role' }))

    await waitFor(() => expect(deleteWorkspaceTeamRole).toHaveBeenCalledWith('safari_review_team', 'role_3'))
  })

  it('rolls optimistic member role changes back when the API rejects the update', async () => {
    // Given
    seedDashboard()
    putWorkspaceTeamMember.mockRejectedValue(new Error('role update failed'))
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)
    fireEvent.change(await screen.findByLabelText('Code Reviewer role'), {
      target: { value: 'member' },
    })

    // Then
    await waitFor(() => expect(showSnackbar).toHaveBeenCalledWith({
      type: 'error',
      message: 'role update failed',
    }))
    expect(screen.getByLabelText('Code Reviewer role')).toHaveValue('reviewer')
  })

  it('rolls failed team creation back to the previous selected team', async () => {
    // Given
    seedDashboard()
    createWorkspaceTeam.mockRejectedValue(new Error('create failed'))
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /new team/i }))

    // Then
    await waitFor(() => expect(showSnackbar).toHaveBeenCalledWith({
      type: 'error',
      message: 'create failed',
    }))
    expect(screen.getByLabelText('Team display name')).toHaveValue('Safari Review Team')
    expect(screen.queryByText('No teams yet. Use New team to create one.')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('New Team')).not.toBeInTheDocument()
  })

  it('does not offer agents already assigned to another workspace team', async () => {
    // Given
    seedDashboard([
      team(),
      team({
        id: 'docs_team',
        display_name: 'Docs Team',
        role_assignments: {},
        members: [],
        member_details: [],
        diagnostics: [],
      }),
    ])
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /Docs Team.*0 agents.*2 roles/i }))

    // Then
    expect(await screen.findByRole('button', { name: 'Add Technical Writer' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add Code Reviewer' })).not.toBeInTheDocument()
  })

  it('keeps core team data visible when the optional agent roster load aborts', async () => {
    // Given
    seedDashboard()
    listAgents.mockRejectedValue(new DOMException('Fetch is aborted', 'AbortError'))
    const { WorkspaceTeamsPanel } = await import('../components/WorkspaceTeamsPanel')

    // When
    render(<WorkspaceTeamsPanel />)

    // Then
    expect(await screen.findByRole('button', { name: /Safari Review Team.*1 agents.*2 roles/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Team display name')).toHaveValue('Safari Review Team')
    expect(screen.getByText('Code Reviewer')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('No available agents')).toBeInTheDocument())
    expect(showSnackbar).not.toHaveBeenCalledWith(expect.objectContaining({
      message: 'Fetch is aborted',
    }))
  })
})
