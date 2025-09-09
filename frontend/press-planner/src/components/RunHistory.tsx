import { useState, useEffect } from 'react'
import { ApiClient } from '../services/apiClient'
import './RunHistory.css'

interface RunHistoryProps {
  apiClient: ApiClient
  onSelectRun: (runId: string) => void
}

interface RunSummary {
  id: string
  query: string | null
  created_at: string
  n_records: number
  n_appraised: number
  label_counts?: {
    Red?: number
    Amber?: number
    Green?: number
  }
}

interface RunsPageResponse {
  total: number
  limit: number
  offset: number
  items: RunSummary[]
}

export function RunHistory({ apiClient, onSelectRun }: RunHistoryProps) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')
  const [currentPage, setCurrentPage] = useState(0)
  const [totalRuns, setTotalRuns] = useState(0)
  const pageSize = 10

  useEffect(() => {
    fetchRuns()
  }, [currentPage])

  const fetchRuns = async () => {
    setLoading(true)
    setError('')
    
    try {
      const data = await apiClient.getRuns(pageSize, currentPage * pageSize)
      setRuns(data.items)
      setTotalRuns(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs history')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/New_York'
    })
  }

  const truncateQuery = (query: string | null | undefined, maxLength: number = 80) => {
    if (!query) return 'Literature Review (No query description)'
    if (query.length <= maxLength) return query
    return query.slice(0, maxLength) + '...'
  }

  const getTotalPages = () => Math.ceil(totalRuns / pageSize)

  const getQualityBreakdown = (labelCounts?: { Red?: number; Amber?: number; Green?: number }) => {
    if (!labelCounts) return null
    
    const red = labelCounts.Red || 0
    const amber = labelCounts.Amber || 0
    const green = labelCounts.Green || 0
    const total = red + amber + green
    
    if (total === 0) return null
    
    return (
      <div className="quality-breakdown-mini">
        <span className="quality-mini red">{red}</span>
        <span className="quality-mini amber">{amber}</span>
        <span className="quality-mini green">{green}</span>
      </div>
    )
  }

  if (loading && runs.length === 0) {
    return (
      <div className="run-history">
        <h2>Literature Review History</h2>
        <div className="loading">Loading runs history...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="run-history">
        <h2>Literature Review History</h2>
        <div className="error">
          <p>Error loading runs history: {error}</p>
          <button onClick={fetchRuns} className="retry-button">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="run-history">
      <div className="run-history-header">
        <h2>Literature Review History</h2>
        <p className="total-runs">Total runs: {totalRuns}</p>
      </div>

      {runs.length === 0 ? (
        <div className="no-runs">
          <p>No literature reviews found. Start by creating your first review!</p>
        </div>
      ) : (
        <>
          <div className="runs-grid">
            {runs.map((run) => (
              <div 
                key={run.id} 
                className="run-card"
                onClick={() => onSelectRun(run.id)}
              >
                <div className="run-card-header">
                  <div className="run-date">{formatDate(run.created_at)}</div>
                  {getQualityBreakdown(run.label_counts)}
                </div>
                
                <div className="run-query">
                  <h3>{truncateQuery(run.query)}</h3>
                </div>
                
                <div className="run-stats">
                  <div className="stat">
                    <span className="stat-number">{run.n_records}</span>
                    <span className="stat-label">Records</span>
                  </div>
                  <div className="stat">
                    <span className="stat-number">{run.n_appraised}</span>
                    <span className="stat-label">Appraised</span>
                  </div>
                </div>
                
                <div className="run-card-footer">
                  <span className="run-id">ID: {run.id.slice(0, 8)}...</span>
                  <button className="view-button">View Results</button>
                </div>
              </div>
            ))}
          </div>

          {getTotalPages() > 1 && (
            <div className="pagination">
              <button 
                onClick={() => setCurrentPage(currentPage - 1)}
                disabled={currentPage === 0}
                className="pagination-button"
              >
                Previous
              </button>
              
              <span className="pagination-info">
                Page {currentPage + 1} of {getTotalPages()}
              </span>
              
              <button 
                onClick={() => setCurrentPage(currentPage + 1)}
                disabled={currentPage >= getTotalPages() - 1}
                className="pagination-button"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}