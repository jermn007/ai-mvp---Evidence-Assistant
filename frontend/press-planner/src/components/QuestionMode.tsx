import type { ApiClient } from '../services/apiClient'

interface QuestionModeProps {
  question: string
  onChange: (question: string) => void
  disabled?: boolean
  onExtractLico?: () => void
  onEnhanceQuestion?: () => void
  canExtractLico?: boolean
  canEnhance?: boolean
  loading?: boolean
  apiClient: ApiClient
}

export function QuestionMode({
  question,
  onChange,
  disabled = false,
  onExtractLico,
  onEnhanceQuestion,
  canExtractLico = false,
  canEnhance = false,
  loading = false
}: QuestionModeProps) {
  return (
    <div className="question-mode">
      <p className="mode-description">
        Write your complete research question and let AI help enhance it or extract LICO components
      </p>

      <div className="question-field">
        <label htmlFor="research-question">
          <strong>Research Question</strong>
          <span className="field-hint">
            What specific question does your systematic review aim to answer?
          </span>
        </label>
        <textarea
          id="research-question"
          value={question}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g., What is the effectiveness of simulation-based learning compared to traditional lecture-based methods on clinical skill acquisition among nursing students in undergraduate programs?"
          disabled={disabled}
          rows={4}
          className="question-textarea"
        />
      </div>

      <div className="question-actions">
        {onEnhanceQuestion && (
          <button
            className="action-btn enhance-btn"
            onClick={onEnhanceQuestion}
            disabled={!canEnhance || loading}
          >
            {loading ? (
              <>
                <span className="spinner">⏳</span>
                Enhancing...
              </>
            ) : (
              <>
                <span className="ai-icon">✨</span>
                Enhance Question
              </>
            )}
          </button>
        )}

        {onExtractLico && (
          <button
            className="action-btn extract-btn"
            onClick={onExtractLico}
            disabled={!canExtractLico || loading}
          >
            {loading ? (
              <>
                <span className="spinner">⏳</span>
                Extracting LICO...
              </>
            ) : (
              <>
                <span className="ai-icon">🔤</span>
                Extract LICO Components
              </>
            )}
          </button>
        )}
      </div>

      <div className="action-hints">
        <p className="action-hint">
          <strong>Enhance:</strong> AI will improve the clarity and academic structure of your question
        </p>
        <p className="action-hint">
          <strong>Extract LICO:</strong> AI will identify and populate the LICO components from your question
        </p>
      </div>
    </div>
  )
}