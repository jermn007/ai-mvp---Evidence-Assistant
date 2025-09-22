import { useState, useCallback, useMemo } from 'react'
import type { LICO, ApiClient } from '../services/apiClient'
import { LicoMode } from './LicoMode'
import { QuestionMode } from './QuestionMode'
import { LicoSearchPreview } from './LicoSearchPreview'
import { useValidation, useApiErrorHandler } from '../hooks/useValidation'
import { validateLico, validateResearchQuestion } from '../utils/validation'
import './ResearchInput.css'

interface ResearchInputProps {
  lico: LICO
  onLicoChange: (field: keyof LICO, value: string) => void
  researchQuestion: string
  onResearchQuestionChange: (question: string) => void
  apiClient: ApiClient
  aiAvailable: boolean
  disabled?: boolean
}

type InputMode = 'lico' | 'question'

export function ResearchInput({
  lico,
  onLicoChange,
  researchQuestion,
  onResearchQuestionChange,
  apiClient,
  aiAvailable,
  disabled = false
}: ResearchInputProps) {
  const [mode, setMode] = useState<InputMode>('lico')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string>('')

  // Enhanced validation and error handling
  const { validationState, validateLicoForm, validateQuestionForm, setApiError, clearValidation } = useValidation()
  const { apiError, isRateLimited, retryAfter, handleApiError, clearError } = useApiErrorHandler()

  const hasLicoContent = Object.values(lico).some(value => value.trim() !== '')
  const hasQuestionContent = researchQuestion.trim() !== ''

  // Validate current data when mode or content changes using useMemo to prevent infinite renders
  const isCurrentModeValid = useMemo(() => {
    if (mode === 'lico') {
      return validateLico(lico).isValid
    } else {
      return validateResearchQuestion(researchQuestion).isValid
    }
  }, [mode, lico, researchQuestion])

  const handleModeToggle = (newMode: InputMode) => {
    setMode(newMode)
    setMessage('')
    clearError()
    clearValidation()
  }

  const handleGenerateQuestion = useCallback(async () => {
    // Validate LICO first
    const licoValidation = validateLicoForm(lico)
    if (!licoValidation.isValid) {
      setMessage('❌ Please fix LICO validation errors before generating a question')
      return
    }

    if (!hasLicoContent) {
      setMessage('Please fill in at least one LICO component first')
      return
    }

    // Check if rate limited
    if (isRateLimited) {
      setMessage(`⏱️ Rate limited. Please wait ${retryAfter} seconds before trying again.`)
      return
    }

    setLoading(true)
    setMessage('')
    clearError()

    try {
      const result = await apiClient.generateResearchQuestion(lico)
      onResearchQuestionChange(result.question)
      setMode('question')
      setMessage('✅ Research question generated successfully!')
    } catch (error) {
      console.error('Error generating question:', error)
      handleApiError(error as Error)

      // Set user-friendly message based on error type
      const err = error as any
      if (err.isRateLimit) {
        setMessage(`⏱️ ${err.message}`)
      } else if (err.isValidation) {
        setMessage(`❌ Validation error: ${err.message}`)
        setApiError(err)
      } else {
        setMessage(`❌ Failed to generate question: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [apiClient, lico, hasLicoContent, onResearchQuestionChange, validateLicoForm, isRateLimited, retryAfter, handleApiError, clearError, setApiError])

  const handleExtractLico = useCallback(async () => {
    if (!hasQuestionContent) {
      setMessage('Please enter a research question first')
      return
    }

    setLoading(true)
    setMessage('')

    try {
      const result = await apiClient.extractLicoFromQuestion(researchQuestion)

      // Update each LICO field (set unconditionally to reflect extraction)
      Object.entries(result.lico).forEach(([key, value]) => {
        const val = typeof value === 'string' ? value : (value ?? '')
        onLicoChange(key as keyof LICO, val)
      })
      setMode('lico')
      setMessage('✅ LICO components extracted successfully!')
    } catch (error) {
      console.error('Error extracting LICO:', error)
      setMessage(`❌ Failed to extract LICO: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [apiClient, researchQuestion, hasQuestionContent, onLicoChange])

  return (
    <div className="card research-input">
      <h3>1️⃣ Define Your Research Question</h3>
      <p>Choose your preferred approach to define the research focus</p>

      {/* Enhanced message display with validation and rate limiting awareness */}
      {(message || apiError || validationState.hasErrors || validationState.hasWarnings) && (
        <div className="message-container">
          {message && (
            <div className={`message ${message.includes('✅') ? 'success' : message.includes('⏱️') ? 'rate-limit' : 'error'}`}>
              {message}
            </div>
          )}

          {apiError && (
            <div className={`message ${isRateLimited ? 'rate-limit' : 'error'}`}>
              {isRateLimited && retryAfter > 0 && (
                <div className="rate-limit-countdown">
                  Rate limited. Retry in {retryAfter}s
                </div>
              )}
              {apiError}
            </div>
          )}

          {validationState.hasErrors && (
            <div className="message validation-error">
              <div className="validation-title">⚠️ Validation Errors:</div>
              <div className="validation-details">{validationState.errorMessage}</div>
            </div>
          )}

          {validationState.hasWarnings && !validationState.hasErrors && (
            <div className="message validation-warning">
              <div className="validation-title">💡 Suggestions:</div>
              <div className="validation-details">{validationState.warningMessage}</div>
            </div>
          )}
        </div>
      )}

      {/* Mode Toggle */}
      <div className="mode-toggle">
        <button
          className={`mode-button ${mode === 'lico' ? 'active' : ''}`}
          onClick={() => handleModeToggle('lico')}
          disabled={disabled}
        >
          <div className="mode-icon">🔤</div>
          <div className="mode-title">LICO Components</div>
          <div className="mode-subtitle">Define Learner, Intervention, Context, Outcome</div>
        </button>

        <div className="mode-divider">
          <span className="divider-text">OR</span>
        </div>

        <button
          className={`mode-button ${mode === 'question' ? 'active' : ''}`}
          onClick={() => handleModeToggle('question')}
          disabled={disabled}
        >
          <div className="mode-icon">❓</div>
          <div className="mode-title">Research Question</div>
          <div className="mode-subtitle">Write your complete research question</div>
        </button>
      </div>

      {/* Input Content */}
      <div className="input-content">
        {mode === 'lico' ? (
          <>
            <LicoMode
              lico={lico}
              onChange={onLicoChange}
              disabled={disabled || loading}
              onGenerateQuestion={aiAvailable ? handleGenerateQuestion : undefined}
              canGenerateQuestion={hasLicoContent && aiAvailable}
              loading={loading}
            />
            <LicoSearchPreview
              lico={lico}
              apiClient={apiClient}
              disabled={disabled || loading}
            />
          </>
        ) : (
          <QuestionMode
            question={researchQuestion}
            onChange={onResearchQuestionChange}
            disabled={disabled || loading}
            onExtractLico={aiAvailable ? handleExtractLico : undefined}
            onEnhanceQuestion={aiAvailable ? async () => {
              if (!hasQuestionContent) return
              setLoading(true)
              try {
                const result = await apiClient.enhanceResearchQuestion(researchQuestion)
                onResearchQuestionChange(result.enhanced_question)
                setMessage('✅ Research question enhanced!')
              } catch (error) {
                setMessage(`❌ Enhancement failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
              } finally {
                setLoading(false)
              }
            } : undefined}
            canExtractLico={hasQuestionContent && aiAvailable}
            canEnhance={hasQuestionContent && aiAvailable}
            loading={loading}
            apiClient={apiClient}
          />
        )}
      </div>
    </div>
  )
}
