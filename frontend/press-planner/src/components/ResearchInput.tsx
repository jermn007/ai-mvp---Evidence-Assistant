import { useState, useCallback } from 'react'
import type { LICO, ApiClient } from '../services/apiClient'
import { LicoMode } from './LicoMode'
import { QuestionMode } from './QuestionMode'
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

  const hasLicoContent = Object.values(lico).some(value => value.trim() !== '')
  const hasQuestionContent = researchQuestion.trim() !== ''

  const handleModeToggle = (newMode: InputMode) => {
    setMode(newMode)
    setMessage('')
  }

  const handleGenerateQuestion = useCallback(async () => {
    if (!hasLicoContent) {
      setMessage('Please fill in at least one LICO component first')
      return
    }

    setLoading(true)
    setMessage('')

    try {
      const result = await apiClient.generateResearchQuestion(lico)
      onResearchQuestionChange(result.question)
      setMode('question')
      setMessage('✅ Research question generated successfully!')
    } catch (error) {
      console.error('Error generating question:', error)
      setMessage(`❌ Failed to generate question: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [apiClient, lico, hasLicoContent, onResearchQuestionChange])

  const handleExtractLico = useCallback(async () => {
    console.log('handleExtractLico called', { hasQuestionContent, researchQuestion: researchQuestion.substring(0, 50) + '...' })
    
    if (!hasQuestionContent) {
      setMessage('Please enter a research question first')
      return
    }

    setLoading(true)
    setMessage('')

    try {
      console.log('Calling extractLicoFromQuestion API')
      const result = await apiClient.extractLicoFromQuestion(researchQuestion)
      console.log('Extract LICO result:', result)
      
      // Update each LICO field (set unconditionally to reflect extraction)
      Object.entries(result.lico).forEach(([key, value]) => {
        const val = typeof value === 'string' ? value : (value ?? '')
        console.log(`Updating LICO field ${key} with value:`, val)
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

      {message && (
        <div className={`message ${message.includes('✅') ? 'success' : 'error'}`}>
          {message}
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
          <LicoMode
            lico={lico}
            onChange={onLicoChange}
            disabled={disabled || loading}
            onGenerateQuestion={aiAvailable ? handleGenerateQuestion : undefined}
            canGenerateQuestion={hasLicoContent && aiAvailable}
            loading={loading}
          />
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
