import type { LICO } from '../services/apiClient'
import './LicoForm.css'

interface LicoFormProps {
  lico: LICO
  onChange: (field: keyof LICO, value: string) => void
  disabled?: boolean
}

export function LicoForm({ lico, onChange, disabled = false }: LicoFormProps) {
  return (
    <div className="lico-form">
      <div className="lico-grid">
        <div className="lico-field">
          <label htmlFor="learner">
            <strong>L</strong>earner
            <span className="field-description">Target population</span>
          </label>
          <input
            id="learner"
            type="text"
            value={lico.learner}
            onChange={(e) => onChange('learner', e.target.value)}
            placeholder="e.g., prelicensure nursing students"
            disabled={disabled}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="intervention">
            <strong>I</strong>ntervention
            <span className="field-description">What is being studied</span>
          </label>
          <input
            id="intervention"
            type="text"
            value={lico.intervention}
            onChange={(e) => onChange('intervention', e.target.value)}
            placeholder="e.g., simulation-based learning"
            disabled={disabled}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="context">
            <strong>C</strong>ontext
            <span className="field-description">Setting or environment</span>
          </label>
          <input
            id="context"
            type="text"
            value={lico.context}
            onChange={(e) => onChange('context', e.target.value)}
            placeholder="e.g., university and clinical settings"
            disabled={disabled}
          />
        </div>

        <div className="lico-field">
          <label htmlFor="outcome">
            <strong>O</strong>utcome
            <span className="field-description">Measured results</span>
          </label>
          <input
            id="outcome"
            type="text"
            value={lico.outcome}
            onChange={(e) => onChange('outcome', e.target.value)}
            placeholder="e.g., skills and attitudes"
            disabled={disabled}
          />
        </div>
      </div>
    </div>
  )
}