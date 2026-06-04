import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('Retail ML Serving Demo UI', () => {
  it('renders the three use cases and architecture services from the spec', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /Retail ML Serving Demo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Recommendations/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Search Ranking/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Dynamic Pricing/i })).toBeInTheDocument()

    const observability = screen.getByLabelText('Serving observability')
    expect(within(observability).getByText('BigQuery')).toBeInTheDocument()
    expect(within(observability).getByText('AlloyDB ScaNN')).toBeInTheDocument()
    expect(within(observability).getByText('Bigtable')).toBeInTheDocument()
    expect(within(observability).getByText('Vertex AI')).toBeInTheDocument()
  })

  it('runs a search workflow and exposes hybrid SQL/debug information', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Search Ranking/i }))
    await user.clear(screen.getByLabelText('Retail search query'))
    await user.type(screen.getByLabelText('Retail search query'), 'trail jacket')
    await user.click(screen.getByRole('button', { name: /Run pipeline/i }))

    expect(screen.getByRole('heading', { name: /TrailShield Rain Jacket/i })).toBeInTheDocument()
    expect(screen.getByText(/combined_score/i)).toBeInTheDocument()
    expect(screen.getByText(/keyword rank preserved/i)).toBeInTheDocument()
  })

  it('simulates a live event and updates feature freshness and decisions', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Dynamic Pricing/i }))
    const viewsBefore = screen.getByLabelText('item views 24h').textContent

    await user.click(screen.getByRole('button', { name: /Simulate product view/i }))

    expect(screen.getByLabelText('item views 24h').textContent).not.toBe(viewsBefore)
    expect(screen.getByText('0s fresh')).toBeInTheDocument()
    expect(screen.getByText(/Live event stream/i)).toBeInTheDocument()
    expect(screen.getByText(/product_viewed/i)).toBeInTheDocument()
  })
})
