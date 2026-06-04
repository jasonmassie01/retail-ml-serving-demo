import { Gauge, Tag } from 'lucide-react'
import type { ServingDecision } from '../domain/types'

interface ProductResultsProps {
  decision: ServingDecision
}

export function ProductResults({ decision }: ProductResultsProps) {
  return (
    <section className="results-panel" aria-label="Pipeline results">
      {decision.results.map((result, index) => (
        <article className="product-row" key={result.product.id}>
          <div className="product-rank">{index + 1}</div>
          <div className="product-copy">
            <h3>{result.product.name}</h3>
            <p>{result.product.description}</p>
            <div className="score-strip">
              <span>Vector {result.retrieval.vectorSimilarity.toFixed(3)}</span>
              <span>Text {result.retrieval.textRank.toFixed(3)}</span>
              <span>Combined {result.retrieval.combinedScore.toFixed(3)}</span>
              <span>Model {result.modelScore.toFixed(3)}</span>
            </div>
            <small>{result.explanation}</small>
          </div>
          <div className="decision-column">
            <strong>${result.product.retailPrice.toFixed(2)}</strong>
            {result.priceDecision ? (
              <>
                <span>
                  <Gauge aria-hidden="true" />
                  ${result.priceDecision.finalPrice.toFixed(2)}
                </span>
                <span>
                  <Tag aria-hidden="true" />
                  {result.priceDecision.couponTier}
                </span>
              </>
            ) : (
              <span>{result.product.brand}</span>
            )}
          </div>
        </article>
      ))}
    </section>
  )
}
