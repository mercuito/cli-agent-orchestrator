import { describe, expect, it } from 'vitest'
import { eventTimelineViewRegistry } from '../components/timelineEventViews'
import { CAO_EVENT_TYPE_KEYS } from '../generated/caoEventPayloadTypes'

describe('eventTimelineViewRegistry', () => {
  it('registers a taught timeline view for every generated CAO event type key', () => {
    // Given
    const fallbackView = eventTimelineViewRegistry.viewFor('unknown.event.Type')

    // When
    const taughtViews = Object.values(CAO_EVENT_TYPE_KEYS).map(eventTypeKey =>
      eventTimelineViewRegistry.viewFor(eventTypeKey),
    )

    // Then
    taughtViews.forEach(view => {
      expect(view).not.toBe(fallbackView)
    })
  })
})
