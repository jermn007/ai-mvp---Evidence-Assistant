import type { LICOEnhancement } from '../services/apiClient'
import './AiAssistant.css'

interface AiAssistantProps {
  onSuggestTemplate: () => void
  onEnhanceLico: () => void
  aiEnhancement: LICOEnhancement | null
  loading: boolean
}

export function AiAssistant({ 
  onSuggestTemplate, 
  onEnhanceLico, 
  aiEnhancement, 
  loading 
}: AiAssistantProps) {
  return (
    <div className="card ai-assistant">
      <h3>🤖 AI Assistant</h3>
      
      <div className="ai-actions">
        <button
          className="ai-action-btn template-btn"
          onClick={onSuggestTemplate}
          disabled={loading}
          title="Get AI recommendation for best template"
        >
          {loading ? "🔄 Processing..." : "🎯 Smart Template"}
        </button>
        
        <button
          className="ai-action-btn enhance-btn"
          onClick={onEnhanceLico}
          disabled={loading}
          title="Get AI suggestions for improving LICO terms"
        >
          {loading ? "🔄 Processing..." : "💡 Enhance LICO"}
        </button>
      </div>

      {aiEnhancement && (
        <div className="ai-enhancement-results">
          <h4>🧠 AI Enhancement Suggestions</h4>
          
          <div className="enhancement-tabs">
            <div className="tab-content">
              <h5>📝 Term Suggestions</h5>
              <div className="suggestion-grid">
                {aiEnhancement.learner_suggestions.length > 0 && (
                  <div className="suggestion-category">
                    <strong>Learner terms:</strong>
                    <div className="suggestion-tags">
                      {aiEnhancement.learner_suggestions.map((term, index) => (
                        <span key={index} className="suggestion-tag">{term}</span>
                      ))}
                    </div>
                  </div>
                )}
                
                {aiEnhancement.intervention_suggestions.length > 0 && (
                  <div className="suggestion-category">
                    <strong>Intervention terms:</strong>
                    <div className="suggestion-tags">
                      {aiEnhancement.intervention_suggestions.map((term, index) => (
                        <span key={index} className="suggestion-tag">{term}</span>
                      ))}
                    </div>
                  </div>
                )}
                
                {aiEnhancement.context_suggestions.length > 0 && (
                  <div className="suggestion-category">
                    <strong>Context terms:</strong>
                    <div className="suggestion-tags">
                      {aiEnhancement.context_suggestions.map((term, index) => (
                        <span key={index} className="suggestion-tag">{term}</span>
                      ))}
                    </div>
                  </div>
                )}
                
                {aiEnhancement.outcome_suggestions.length > 0 && (
                  <div className="suggestion-category">
                    <strong>Outcome terms:</strong>
                    <div className="suggestion-tags">
                      {aiEnhancement.outcome_suggestions.map((term, index) => (
                        <span key={index} className="suggestion-tag">{term}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {Object.keys(aiEnhancement.mesh_suggestions).length > 0 && (
              <div className="tab-content">
                <h5>🏷️ MeSH Terms</h5>
                <div className="mesh-suggestions">
                  {Object.entries(aiEnhancement.mesh_suggestions).map(([category, terms]) => (
                    terms.length > 0 && (
                      <div key={category} className="mesh-category">
                        <strong>{category.charAt(0).toUpperCase() + category.slice(1)}:</strong>
                        <div className="mesh-tags">
                          {terms.map((term, index) => (
                            <span key={index} className="mesh-tag">{term}</span>
                          ))}
                        </div>
                      </div>
                    )
                  ))}
                </div>
              </div>
            )}

            <div className="tab-content">
              <h5>💭 Analysis</h5>
              <div className="ai-analysis">
                <div className="analysis-item">
                  <strong>Template Recommendation:</strong>
                  <span className="recommendation-badge">
                    {aiEnhancement.template_recommendation}
                  </span>
                </div>
                <div className="analysis-item">
                  <strong>Explanation:</strong>
                  <p>{aiEnhancement.explanation}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}