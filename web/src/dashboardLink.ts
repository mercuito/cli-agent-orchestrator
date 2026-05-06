export type TabKey = 'home' | 'agents' | 'flows' | 'settings'

export interface InitialDashboardView {
  tab: TabKey
  terminalId: string | null
  terminalToken: string | null
  agentId: string | null
  agentToken: string | null
}

function isTabKey(value: string | null): value is TabKey {
  return value === 'home' || value === 'agents' || value === 'flows' || value === 'settings'
}

export function parseInitialDashboardView(search: string): InitialDashboardView {
  const params = new URLSearchParams(search)
  const terminalId = params.get('terminal_id') || params.get('terminalId')
  const terminalToken = params.get('terminal_token') || params.get('terminalToken')
  const agentId = params.get('agent_id') || params.get('agentId')
  const agentToken = params.get('agent_token') || params.get('agentToken')
  const tab = params.get('tab')

  return {
    tab: terminalId || agentId ? 'agents' : isTabKey(tab) ? tab : 'home',
    terminalId,
    terminalToken,
    agentId,
    agentToken,
  }
}
