import { useState, useEffect } from 'react'
import type { LICO, ApiClient } from '../services/apiClient'
import './LicoSearchPreview.css'

interface LicoSearchPreviewProps {
  lico: LICO
  apiClient: ApiClient
  disabled?: boolean
}

interface PreviewData {
  lico_input: LICO
  extracted_terms: Record<string, string[]>
  merged_terms: Record<string, {
    user_extracted: string[]
    yaml_mesh: string[]
    yaml_text: string[]
    final_mesh: string[]
    final_text: string[]
  }>
  sample_strategy: any
  message: string
}

export function LicoSearchPreview({ lico, apiClient, disabled = false }: LicoSearchPreviewProps) {
  const [loading, setLoading] = useState(false)
  const [previewData, setPreviewData] = useState<PreviewData | null>(null)
  const [error, setError] = useState<string>('')
  const [expanded, setExpanded] = useState(false)

  // Check if LICO has any content to preview
  const hasLicoContent = Object.values(lico).some(value => value.trim() !== '')

  const loadPreview = async () => {
    if (!hasLicoContent) {
      setError('Enter some LICO content to see search term preview')
      return
    }

    setLoading(true)
    setError('')

    try {
      const data = await apiClient.previewPressStrategy(lico)
      setPreviewData(data)
      setExpanded(true)
    } catch (err) {
      console.error('Error loading LICO preview:', err)
      setError(`Failed to load preview: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  // Auto-load preview when LICO content changes (debounced)
  useEffect(() => {
    if (!hasLicoContent) {
      setPreviewData(null)
      setExpanded(false)
      return
    }

    const timer = setTimeout(() => {
      if (!disabled) {
        loadPreview()
      }
    }, 1000) // 1 second debounce

    return () => clearTimeout(timer)
  }, [lico.learner, lico.intervention, lico.context, lico.outcome, disabled])

  const renderTermGroup = (title: string, component: string) => {
    if (!previewData?.merged_terms[component]) return null

    const terms = previewData.merged_terms[component]
    const hasUserTerms = terms.user_extracted.length > 0
    const hasYamlTerms = terms.yaml_mesh.length > 0 || terms.yaml_text.length > 0

    if (!hasUserTerms && !hasYamlTerms) return null

    return (
      <div key={component} className="term-group">
        <h4 className="term-group-title">{title}</h4>

        {hasUserTerms && (
          <div className="term-section">
            <div className="term-section-header">
              <span className="term-badge user-terms">Your Terms</span>
              <span className="term-count">({terms.user_extracted.length})</span>
            </div>
            <div className="term-list">
              {terms.user_extracted.map((term, idx) => (
                <span key={idx} className="term-chip user-term">{term}</span>
              ))}
            </div>
          </div>
        )}

        {hasYamlTerms && (
          <div className="term-section">
            <div className="term-section-header">
              <span className="term-badge system-terms">System Terms</span>
              <span className="term-count">({terms.yaml_mesh.length + terms.yaml_text.length})</span>
            </div>
            <div className="term-list">
              {terms.yaml_mesh.map((term, idx) => (
                <span key={`mesh-${idx}`} className="term-chip mesh-term" title="MeSH Term">{term}</span>
              ))}
              {terms.yaml_text.map((term, idx) => (
                <span key={`text-${idx}`} className="term-chip text-term" title="Text Term">{term}</span>
              ))}
            </div>
          </div>
        )}

        <div className="final-terms">
          <div className="term-section-header">
            <span className="term-badge final-terms">Final Search Terms</span>
            <span className="term-count">({terms.final_mesh.length + terms.final_text.length})</span>
          </div>
          <div className="term-list">
            {terms.final_mesh.map((term, idx) => (
              <span key={`final-mesh-${idx}`} className="term-chip final-mesh-term">{term}</span>
            ))}
            {terms.final_text.map((term, idx) => (
              <span key={`final-text-${idx}`} className="term-chip final-text-term">{term}</span>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!hasLicoContent) {
    return (
      <div className="lico-search-preview empty">
        <div className="preview-header">
          <div className="preview-icon">🔍</div>
          <div className="preview-title">Search Terms Preview</div>
        </div>
        <p className="empty-message">Enter LICO components above to see how they'll be converted into search terms</p>
      </div>
    )
  }

  return (
    <div className="lico-search-preview">
      <div className="preview-header">
        <div className="preview-icon">🔍</div>
        <div className="preview-title">Search Terms Preview</div>
        <button
          className={`preview-toggle ${expanded ? 'expanded' : 'collapsed'}`}
          onClick={() => expanded ? setExpanded(false) : loadPreview()}
          disabled={loading || disabled}
        >
          {loading ? '⏳ Loading...' : expanded ? '▼ Hide Preview' : '▶ Show Preview'}
        </button>
      </div>

      {error && (
        <div className="preview-error">
          ⚠️ {error}
        </div>
      )}

      {expanded && previewData && (
        <div className="preview-content">
          <div className="preview-message">
            💡 {previewData.message}
          </div>

          <div className="terms-container">
            {renderTermGroup('👥 Learner', 'learner')}
            {renderTermGroup('🎯 Intervention', 'intervention')}
            {renderTermGroup('🌍 Context', 'context')}
            {renderTermGroup('📊 Outcome', 'outcome')}
          </div>

          {previewData.sample_strategy?.lines && (
            <div className="strategy-preview">
              <h4>Sample PubMed Search Strategy</h4>
              <div className="strategy-lines">
                {previewData.sample_strategy.lines.map((line: any, idx: number) => (
                  <div key={idx} className="strategy-line">
                    <span className="line-number">{line.n}</span>
                    <span className="line-type">{line.type}</span>
                    <span className="line-text">{line.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}