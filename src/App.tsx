import { useMemo, useState } from 'react'
import { Play, RadioTower, RotateCw } from 'lucide-react'
import './App.css'
import { ObservabilityRail } from './components/ObservabilityRail'
import { ProductResults } from './components/ProductResults'
import { UseCaseNav } from './components/UseCaseNav'
import { catalog, createInitialFeatureStore, users } from './data/retailDemoData'
import { applyLiveEvent, runServingPipeline } from './domain/servingEngine'
import type { UseCase } from './domain/types'

const initialNow = new Date('2026-06-04T17:00:00.000Z')

function App() {
  const [activeUseCase, setActiveUseCase] = useState<UseCase>('recommendations')
  const [query, setQuery] = useState('trail jacket for rainy commute')
  const [selectedProductId, setSelectedProductId] = useState('p-trail-jacket')
  const [selectedUserId, setSelectedUserId] = useState(users[0].id)
  const [now, setNow] = useState(initialNow)
  const [featureStore, setFeatureStore] = useState(() => createInitialFeatureStore(initialNow))
  const [runCount, setRunCount] = useState(0)

  const decision = useMemo(() => {
    return runServingPipeline({
      catalog,
      featureStore,
      userId: selectedUserId,
      useCase: activeUseCase,
      query,
      category: 'Outerwear',
      maxPrice: 160,
      productId: selectedProductId,
      now,
    })
  }, [activeUseCase, featureStore, now, query, selectedProductId, selectedUserId])

  const itemFeatures = decision.onlineFeatures.item

  function simulateProductView() {
    const occurredAt = new Date(now.getTime() + 15_000)
    setFeatureStore((current) => {
      return applyLiveEvent(current, {
        productId: selectedProductId,
        type: 'product_viewed',
        occurredAt,
      })
    })
    setNow(occurredAt)
  }

  return (
    <div className="app-shell">
      <UseCaseNav activeUseCase={activeUseCase} onChange={setActiveUseCase} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>Retail ML Serving Demo</h1>
            <p>
              One local retrieve - feature fetch - score/rank path for recommendations,
              search ranking, and dynamic pricing.
            </p>
          </div>
          <div className="run-actions">
            <span className="run-count">Runs {runCount + 1}</span>
            <button
              className="secondary-button"
              onClick={() => setRunCount((count) => count + 1)}
            >
              <RotateCw aria-hidden="true" />
              Run pipeline
            </button>
          </div>
        </header>

        <section className="control-band" aria-label="Demo controls">
          <label>
            User
            <select
              value={selectedUserId}
              onChange={(event) => setSelectedUserId(event.target.value)}
            >
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name} - {user.segment}
                </option>
              ))}
            </select>
          </label>
          <label>
            Product
            <select
              value={selectedProductId}
              onChange={(event) => setSelectedProductId(event.target.value)}
            >
              {catalog.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))}
            </select>
          </label>
          <label className="query-field">
            Retail search query
            <input
              aria-label="Retail search query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </section>

        <section className="live-band" aria-label="Live event stream">
          <div>
            <RadioTower aria-hidden="true" />
            <span>Live event stream</span>
            <strong>{featureStore.eventLog[0]?.type ?? 'waiting_for_event'}</strong>
          </div>
          <button className="primary-button" onClick={simulateProductView} type="button">
            <Play aria-hidden="true" />
            Simulate product view
          </button>
          <div className="metric">
            <span>Item views 24h</span>
            <strong aria-label="item views 24h">{itemFeatures.itemViews24h}</strong>
          </div>
          <div className="metric">
            <span>Demand slope</span>
            <strong>{itemFeatures.demandSlope24h.toFixed(2)}</strong>
          </div>
        </section>

        <ProductResults decision={decision} />

        <section className="debug-panel" aria-label="SQL and debug profile">
          <div>
            <h2>Debug Profile</h2>
            <p>
              BigQuery feature definitions stay offline; local data simulates the same
              Bigtable row-key reads and AlloyDB hybrid candidate contract.
            </p>
          </div>
          <pre>{decision.debugSql}</pre>
        </section>
      </main>
      <ObservabilityRail decision={decision} />
    </div>
  )
}

export default App
