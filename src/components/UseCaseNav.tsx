import {
  BadgeDollarSign,
  Boxes,
  Search,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import type { UseCase } from '../domain/types'

interface UseCaseNavProps {
  activeUseCase: UseCase
  onChange: (useCase: UseCase) => void
}

const items: readonly {
  useCase: UseCase
  label: string
  helper: string
  icon: LucideIcon
}[] = [
  {
    useCase: 'recommendations',
    label: 'Recommendations',
    helper: 'User affinity + item candidates',
    icon: Sparkles,
  },
  {
    useCase: 'search',
    label: 'Search Ranking',
    helper: 'Vector + full-text + filters',
    icon: Search,
  },
  {
    useCase: 'pricing',
    label: 'Dynamic Pricing',
    helper: 'Price floor + coupon propensity',
    icon: BadgeDollarSign,
  },
]

export function UseCaseNav({ activeUseCase, onChange }: UseCaseNavProps) {
  return (
    <nav aria-label="Use cases" className="use-case-nav">
      <div className="nav-brand">
        <Boxes aria-hidden="true" />
        <span>Feature Store</span>
      </div>
      {items.map((item) => {
        const Icon = item.icon
        return (
          <button
            className={item.useCase === activeUseCase ? 'nav-item active' : 'nav-item'}
            key={item.useCase}
            onClick={() => onChange(item.useCase)}
            type="button"
          >
            <Icon aria-hidden="true" />
            <span>
              <strong>{item.label}</strong>
              <small>{item.helper}</small>
            </span>
          </button>
        )
      })}
    </nav>
  )
}
