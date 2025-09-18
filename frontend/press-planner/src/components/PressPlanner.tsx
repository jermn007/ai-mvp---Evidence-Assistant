import { useState, useCallback, useMemo, memo, useEffect } from 'react'
import { ApiClient } from '../services/apiClient'
import type { LICO, LICOEnhancement, PressPlan, AiEnhancedPlan } from '../services/apiClient'
import { ResearchInput } from './ResearchInput'
import { AiAssistant } from './AiAssistant'
import { StrategyDisplay } from './StrategyDisplay'
import { RunResults } from './RunResults'
import './PressPlanner.css'

interface PressPlannerProps {
  apiClient: ApiClient
  aiAvailable: boolean
  onRunComplete?: (runId: string, runData?: any) => void
}

export function PressPlanner({ apiClient, aiAvailable, onRunComplete }: PressPlannerProps) {
  const [lico, setLico] = useState<LICO>({
    learner: '',
    intervention: '',
    context: '',
    outcome: ''
  })

  const [researchQuestion, setResearchQuestion] = useState<string>('')

  const [template, setTemplate] = useState<string>('education')
  const [useStock, setUseStock] = useState<boolean>(true)
  const [enableAi, setEnableAi] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')

  // State for AI enhancements and results
  const [aiEnhancement, setAiEnhancement] = useState<LICOEnhancement | null>(null)
  const [pressPlan, setPressPlan] = useState<PressPlan | null>(null)
  const [strategyAnalysis, setStrategyAnalysis] = useState<any>(null)

  // State for run execution
  const [runResult, setRunResult] = useState<any>(null)
  const [isRunning, setIsRunning] = useState<boolean>(false)

  // Cleanup effect to cancel pending requests
  useEffect(() => {
    return () => {
      apiClient.cancelAllRequests()
    }
  }, [apiClient])

  // Memoize validation logic
  const validationState = useMemo(() => {
    const hasLicoContent = Object.values(lico).some(value => value.trim() !== '')
    const hasQuestionContent = researchQuestion.trim() !== ''
    const canBuildPlan = hasLicoContent || hasQuestionContent
    const canRunWorkflow = pressPlan !== null

    return {
      hasLicoContent,
      hasQuestionContent,
      canBuildPlan,
      canRunWorkflow
    }
  }, [lico, researchQuestion, pressPlan])

  const handleLicoChange = useCallback((field: keyof LICO, value: string) => {
    setLico(prev => ({ ...prev, [field]: value }))
  }, [])

  const handleResearchQuestionChange = useCallback((question: string) => {
    setResearchQuestion(question)
  }, [])

  const handleSuggestTemplate = useCallback(async () => {
    if (!aiAvailable) {
      setError('AI is not available')
      return
    }
    
    console.log('Starting template suggestion with LICO:', lico)
    setLoading(true)
    setError('')
    
    try {
      const suggestion = await apiClient.suggestTemplate(lico)
      console.log('Template suggestion successful:', suggestion)
      setTemplate(suggestion.suggested_template)
      setError(`✅ Suggested template: ${suggestion.suggested_template} - ${suggestion.reasoning}`)
    } catch (err) {
      console.error('Template suggestion failed:', err)
      setError(`Template suggestion failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [apiClient, lico, aiAvailable])

  const handleEnhanceLico = useCallback(async () => {
    if (!aiAvailable) {
      setError('AI is not available')
      return
    }
    
    console.log('Starting LICO enhancement with:', lico)
    setLoading(true)
    setError('')
    
    try {
      const researchDomain = lico.intervention && lico.context 
        ? `${lico.intervention} in ${lico.context}` 
        : undefined
      
      const enhancement = await apiClient.enhanceLico(lico, researchDomain)
      console.log('LICO enhancement successful:', enhancement)
      setAiEnhancement(enhancement)
      setError('✅ LICO enhanced successfully! Check the AI Assistant section for suggestions.')
    } catch (err) {
      console.error('LICO enhancement failed:', err)
      setError(`LICO enhancement failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [apiClient, lico, aiAvailable])

  const handleBuildPlan = useCallback(async () => {
    if (!validationState.canBuildPlan) {
      setError('Please provide either LICO components or a research question')
      return
    }

    setLoading(true)
    setError('')
    setPressPlan(null)
    setStrategyAnalysis(null)

    try {
      let licoToUse = lico

      // If LICO fields are mostly empty but we have a research question, try to extract LICO first
      if (!validationState.hasLicoContent && validationState.hasQuestionContent && aiAvailable) {
        try {
          const extractResult = await apiClient.extractLicoFromQuestion(researchQuestion)
          licoToUse = extractResult.lico
          // Update the state with extracted LICO components (set unconditionally)
          Object.entries(extractResult.lico).forEach(([key, value]) => {
            const val = typeof value === 'string' ? value : (value ?? '')
            handleLicoChange(key as keyof LICO, val)
          })
          setError('✅ LICO components automatically extracted from your research question')
        } catch (extractError) {
          console.warn('Failed to auto-extract LICO:', extractError)
          // Continue with original LICO even if extraction fails
        }
      }
      
      const researchDomain = licoToUse.intervention && licoToUse.context 
        ? `${licoToUse.intervention} in ${licoToUse.context}` 
        : undefined

      const result = await apiClient.createPressPlan({
        lico: licoToUse,
        template,
        useStock,
        enableAi: enableAi && aiAvailable,
        researchDomain
      })

      if ('base_plan' in result) {
        // AI-enhanced response
        const aiResult = result as AiEnhancedPlan
        setPressPlan(aiResult.base_plan)
        if (aiResult.ai_enhancement) {
          setAiEnhancement(aiResult.ai_enhancement)
        }
        if (aiResult.strategy_analysis) {
          setStrategyAnalysis(aiResult.strategy_analysis)
        }
      } else {
        // Standard response
        setPressPlan(result as PressPlan)
      }
    } catch (err) {
      setError(`Plan creation failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [apiClient, lico, researchQuestion, template, useStock, enableAi, aiAvailable, handleLicoChange, validationState])

  const handleRunWithPlan = useCallback(async () => {
    if (!validationState.canRunWorkflow) {
      setError('Please build a PRESS plan first')
      return
    }

    console.log('Starting run execution with plan:', pressPlan)
    setIsRunning(true)
    setError('')

    try {
      const result = await apiClient.runWithPlan(pressPlan!)
      console.log('Run execution started:', result)
      setRunResult(result)
      setError(`✅ Literature review started successfully! Run ID: ${result.run_id}`)

      // Notify parent component about the completed run
      if (onRunComplete && result.run_id) {
        onRunComplete(result.run_id, result)
      }
    } catch (err) {
      console.error('Run execution failed:', err)
      setError(`Run execution failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setIsRunning(false)
    }
  }, [apiClient, pressPlan, validationState.canRunWorkflow, onRunComplete])

  return (
    <div className="press-planner">
      <div className="planner-header">
        <h2>📋 PRESS Strategy Planner</h2>
        <p>Create evidence-based search strategies using the PRESS framework</p>
        
        {error && (
          <div className={`message ${error.includes('✅') ? 'success' : 'error'}`}>
            {error}
          </div>
        )}
      </div>

      <div className="planner-content">
        <div className="planner-main">
          {/* Research Input - Dual Mode */}
          <ResearchInput
            lico={lico}
            onLicoChange={handleLicoChange}
            researchQuestion={researchQuestion}
            onResearchQuestionChange={handleResearchQuestionChange}
            apiClient={apiClient}
            aiAvailable={aiAvailable}
            disabled={loading}
          />

          {/* Status Message Display */}
          {error && (
            <div className={`message ${error.includes('✅') ? 'success' : 'error'}`}>
              {error}
            </div>
          )}

          {/* Strategy Display */}
          {pressPlan && (
            <StrategyDisplay 
              plan={pressPlan}
              currentLico={lico}
              strategyAnalysis={strategyAnalysis}
              apiClient={apiClient}
            />
          )}

          {/* Run Results */}
          {runResult && (
            <RunResults 
              runId={runResult.run_id}
              runData={runResult}
              apiClient={apiClient}
            />
          )}
        </div>

        <div className="planner-sidebar">
          {/* Configuration Options */}
          <div className="card">
            <h3>2️⃣ Configuration</h3>
            <div className="config-options">
              <div className="config-group">
                <label htmlFor="template">Template:</label>
                <select 
                  id="template"
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                  disabled={loading}
                >
                  <option value="education">Education</option>
                  <option value="clinical">Clinical</option>
                  <option value="general">General</option>
                </select>
              </div>

              <div className="config-group">
                <label>
                  <input
                    type="checkbox"
                    checked={useStock}
                    onChange={(e) => setUseStock(e.target.checked)}
                    disabled={loading}
                  />
                  Use stock scaffolds (template terms)
                </label>
              </div>

              {aiAvailable && (
                <div className="config-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={enableAi}
                      onChange={(e) => setEnableAi(e.target.checked)}
                      disabled={loading}
                    />
                    🤖 Enable AI assistance
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* AI Assistant */}
          {enableAi && aiAvailable && (
            <AiAssistant
              onSuggestTemplate={handleSuggestTemplate}
              onEnhanceLico={handleEnhanceLico}
              aiEnhancement={aiEnhancement}
              loading={loading}
            />
          )}

          {/* Build Plan Button */}
          <div className="card">
            <button
              className="build-plan-btn"
              onClick={handleBuildPlan}
              disabled={loading || !validationState.canBuildPlan}
              title={!validationState.canBuildPlan ? 'Please provide LICO components or research question' : ''}
            >
              {loading ? 'Building Plan...' : '🚀 Build PRESS Plan'}
            </button>
          </div>

          {/* Run with Plan Button */}
          {validationState.canRunWorkflow && (
            <div className="card">
              <h3>🚀 Execute Literature Review</h3>
              <p>Run the complete systematic review workflow with your PRESS plan</p>
              <button
                className="build-plan-btn run-btn"
                onClick={handleRunWithPlan}
                disabled={isRunning || loading || !validationState.canRunWorkflow}
              >
                {isRunning ? '⏳ Running Literature Review...' : '🔬 Run with Plan'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
