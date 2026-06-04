import { Activity, Clock, Database, RadioTower } from 'lucide-react'
import { formatFreshness } from '../domain/servingEngine'
import type { ServingDecision } from '../domain/types'

interface ObservabilityRailProps {
  decision: ServingDecision
}

export function ObservabilityRail({ decision }: ObservabilityRailProps) {
  return (
    <aside aria-label="Serving observability" className="observability-rail">
      <div className="rail-heading">
        <Activity aria-hidden="true" />
        <div>
          <h2>Serving Trace</h2>
          <p>Retrieve - fetch - score/rank</p>
        </div>
      </div>

      <ol className="trace-list">
        {decision.trace.map((stage) => (
          <li key={stage.service}>
            <Database aria-hidden="true" />
            <span>
              <strong>{stage.service}</strong>
              <small>{stage.operation}</small>
            </span>
            <b>{stage.latencyMs}ms</b>
          </li>
        ))}
      </ol>

      <div className="freshness-panel">
        <div className="rail-heading compact">
          <Clock aria-hidden="true" />
          <div>
            <h2>Feature Freshness</h2>
            <p>p95 SLA: 2 minutes</p>
          </div>
        </div>
        {decision.freshness.rows.map((row) => (
          <div className="freshness-row" key={row.entityKey}>
            <span>{row.entityKey}</span>
            <strong>{formatFreshness(row.stalenessSeconds)}</strong>
          </div>
        ))}
      </div>

      <div className="event-status">
        <RadioTower aria-hidden="true" />
        <span>Event emulator</span>
        <strong>{decision.eventCount} applied</strong>
      </div>
    </aside>
  )
}
