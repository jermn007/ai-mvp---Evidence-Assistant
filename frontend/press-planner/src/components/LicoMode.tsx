import type { LICO } from '../services/apiClient'

interface LicoModeProps {
  lico: LICO
  onChange: (field: keyof LICO, value: string) => void
  disabled?: boolean
  onGenerateQuestion?: () => void
  canGenerateQuestion?: boolean
  loading?: boolean
}

export function LicoMode({
  lico,
  onChange,
  disabled = false,
  onGenerateQuestion,
  canGenerateQuestion = false,
  loading = false
}: LicoModeProps) {
  return (
    <div className="lico-mode">
      <p className="mode-description">
        Define each component of your research question using the LICO framework
      </p>

      <div className="lico-fields">
        <div className="lico-field">
          <label htmlFor="learner">
            <strong>Learner</strong>
            <span className="field-hint">Who is the target population or learner group?</span>
          </label>
          <textarea
            id="learner"
            value={lico.learner}
            onChange={(e) => onChange('learner', e.target.value)}
            placeholder="e.g., medical students, K-12 teachers, undergraduate nursing students"
            disabled={disabled}
            rows={2}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="intervention">
            <strong>Intervention</strong>
            <span className="field-hint">What educational intervention or approach is being studied?</span>
          </label>
          <textarea
            id="intervention"
            value={lico.intervention}
            onChange={(e) => onChange('intervention', e.target.value)}
            placeholder="e.g., simulation-based learning, flipped classroom, peer tutoring"
            disabled={disabled}
            rows={2}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="context">
            <strong>Context</strong>
            <span className="field-hint">Where or in what setting does the learning occur?</span>
          </label>
          <textarea
            id="context"
            value={lico.context}
            onChange={(e) => onChange('context', e.target.value)}
            placeholder="e.g., clinical setting, online environment, laboratory, classroom"
            disabled={disabled}
            rows={2}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="outcome">
            <strong>Outcome</strong>
            <span className="field-hint">What learning outcomes or effects are being measured?</span>
          </label>
          <textarea
            id="outcome"
            value={lico.outcome}
            onChange={(e) => onChange('outcome', e.target.value)}
            placeholder="e.g., knowledge retention, clinical skills, student satisfaction, learning engagement"
            disabled={disabled}
            rows={2}
          />
        </div>
      </div>

      {onGenerateQuestion && (
        <div className="generate-section">
          <button
            className="generate-btn"
            onClick={onGenerateQuestion}
            disabled={!canGenerateQuestion || loading}
          >
            {loading ? (
              <>
                <span className="spinner">⏳</span>
                Generating Research Question...
              </>
            ) : (
              <>
                <span className="ai-icon">🤖</span>
                Generate Research Question
              </>
            )}
          </button>
          <p className="generate-hint">
            AI will create an academic research question based on your LICO components
          </p>
        </div>
      )}
    </div>
  )
}