import { useState, useEffect } from 'react'
import { ApiClient } from '../services/apiClient'
import type { PressPlan, PressStrategyAnalysis, LICO } from '../services/apiClient'
import './StrategyDisplay.css'

interface StrategyDisplayProps {
  plan: PressPlan
  currentLico?: LICO
  strategyAnalysis?: PressStrategyAnalysis
  apiClient: ApiClient
}

export function StrategyDisplay({ plan, currentLico, strategyAnalysis, apiClient }: StrategyDisplayProps) {
  const [queries, setQueries] = useState<{query_pubmed: string, query_generic: string, years: string} | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const generateQueries = async () => {
      setLoading(true)
      try {
        const queryResult = await apiClient.generateQueries(plan)
        setQueries(queryResult)
      } catch (error) {
        console.error('Failed to generate queries:', error)
      } finally {
        setLoading(false)
      }
    }

    generateQueries()
  }, [plan, apiClient])

  const medlineStrategy = plan.strategies?.MEDLINE
  const lines = medlineStrategy?.lines || []

  return (
    <div className="strategy-display">
      <h3>📋 PRESS Strategy Results</h3>

      {/* Strategy Lines */}
      <div className="card">
        <h4>Search Strategy Lines</h4>
        <div className="strategy-lines">
          {lines.map((line: any, index: number) => (
            <div key={index} className="strategy-line">
              <div className="line-header">
                <span className="line-number">{line.n}</span>
                <span className="line-type">{line.type}</span>
                {line.hits && <span className="hits-count">{line.hits.toLocaleString()} hits</span>}
              </div>
              <div className="line-text">{line.text}</div>
            </div>
          ))}
        </div>
      </div>

      {/* AI Strategy Analysis */}
      {strategyAnalysis && (
        <div className="card ai-analysis">
          <h4>🤖 AI Strategy Analysis</h4>
          <div className="analysis-grid">
            <div className="analysis-metrics">
              <div className="metric">
                <span className="metric-label">Completeness Score</span>
                <span className="metric-value">
                  {(strategyAnalysis.completeness_score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Precision</span>
                <span className={`metric-badge ${strategyAnalysis.estimated_precision.toLowerCase()}`}>
                  {strategyAnalysis.estimated_precision}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Recall</span>
                <span className={`metric-badge ${strategyAnalysis.estimated_recall.toLowerCase()}`}>
                  {strategyAnalysis.estimated_recall}
                </span>
              </div>
            </div>

            <div className="analysis-details">
              <div className="detail-section">
                <strong>Balance Assessment:</strong>
                <p>{strategyAnalysis.balance_assessment}</p>
              </div>

              {strategyAnalysis.missing_components.length > 0 && (
                <div className="detail-section missing-components">
                  <strong>Missing Components:</strong>
                  <ul>
                    {strategyAnalysis.missing_components.map((component, index) => (
                      <li key={index}>{component}</li>
                    ))}
                  </ul>
                </div>
              )}

              {strategyAnalysis.suggestions.length > 0 && (
                <div className="detail-section suggestions">
                  <strong>💡 Improvement Suggestions:</strong>
                  <ol>
                    {strategyAnalysis.suggestions.map((suggestion, index) => (
                      <li key={index}>{suggestion}</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Generated Queries */}
      {loading ? (
        <div className="card">
          <h4>🔍 Query Preview</h4>
          <p>Generating queries...</p>
        </div>
      ) : queries ? (
        <div className="card">
          <h4>🔍 Generated Queries</h4>
          <div className="query-tabs">
            <div className="query-section">
              <h5>📚 PubMed/MEDLINE Query</h5>
              <div className="query-stats">
                <span>Length: {queries.query_pubmed.length} characters</span>
                <span>Years: {queries.years}</span>
              </div>
              <div className="query-text">
                <pre>{queries.query_pubmed}</pre>
              </div>
              <button 
                className="copy-btn"
                onClick={() => navigator.clipboard.writeText(queries.query_pubmed)}
              >
                📋 Copy PubMed Query
              </button>
            </div>

            <div className="query-section">
              <h5>🌐 Generic Query (Other Sources)</h5>
              <div className="query-stats">
                <span>Length: {queries.query_generic.length} characters</span>
                <span>For: Crossref, ERIC, ArXiv, Semantic Scholar, Google Scholar</span>
              </div>
              <div className="query-text">
                <pre>{queries.query_generic}</pre>
              </div>
              <button 
                className="copy-btn"
                onClick={() => navigator.clipboard.writeText(queries.query_generic)}
              >
                📋 Copy Generic Query
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="card">
          <h4>🔍 Query Preview</h4>
          <p>Failed to generate queries. Please try again.</p>
        </div>
      )}

      {/* LICO Summary */}
      <div className="card">
        <h4>🎯 Research Question Summary</h4>
        <div className="lico-summary">
          <div className="lico-item">
            <strong>Learner:</strong> {currentLico?.learner || plan.question_lico?.learner || "—"}
          </div>
          <div className="lico-item">
            <strong>Intervention:</strong> {currentLico?.intervention || plan.question_lico?.intervention || "—"}
          </div>
          <div className="lico-item">
            <strong>Context:</strong> {currentLico?.context || plan.question_lico?.context || "—"}
          </div>
          <div className="lico-item">
            <strong>Outcome:</strong> {currentLico?.outcome || plan.question_lico?.outcome || "—"}
          </div>
        </div>
      </div>
    </div>
  )
}