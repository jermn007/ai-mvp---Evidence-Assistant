import { useState, useEffect, useCallback, useMemo, memo } from 'react'
import './App.css'
import { PressPlanner } from './components/PressPlanner'
import { RunHistory } from './components/RunHistory'
import { RunResults } from './components/RunResults'
import { ApiClient } from './services/apiClient'

// Create singleton API client to avoid recreating on each render
const apiClient = new ApiClient()

type AppView = 'planner' | 'history' | 'results'

// Memoized Loading Component
const LoadingSpinner = memo(() => (
  <div className="loading">
    <div className="spinner"></div>
    <p>Loading Evidence Assistant...</p>
  </div>
))
LoadingSpinner.displayName = 'LoadingSpinner'

function App() {
  const [aiAvailable, setAiAvailable] = useState<boolean>(false)
  const [loading, setLoading] = useState(true)
  const [currentView, setCurrentView] = useState<AppView>('planner')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  useEffect(() => {
    // Check AI status on load
    const checkAiStatus = async () => {
      try {
        const status = await apiClient.checkAiStatus()
        setAiAvailable(status.available)
      } catch (error) {
        console.warn('Failed to check AI status:', error)
        setAiAvailable(false)
      } finally {
        setLoading(false)
      }
    }

    checkAiStatus()
  }, [])

  // Memoize event handlers to prevent unnecessary re-renders
  const handleSelectRun = useCallback((runId: string) => {
    setSelectedRunId(runId)
    setCurrentView('results')
  }, [])

  const handleNewRun = useCallback((runId: string, runData?: any) => {
    setSelectedRunId(runId)
    setCurrentView('results')
  }, [])

  const handleViewChange = useCallback((view: AppView) => {
    setCurrentView(view)
  }, [])

  if (loading) {
    return <LoadingSpinner />
  }

  // Memoize the current view to prevent unnecessary re-renders
  const currentViewComponent = useMemo(() => {
    switch (currentView) {
      case 'history':
        return (
          <RunHistory
            apiClient={apiClient}
            onSelectRun={handleSelectRun}
          />
        )
      case 'results':
        if (!selectedRunId) {
          // Reset to planner if no run selected
          setTimeout(() => setCurrentView('planner'), 0)
          return null
        }
        return (
          <RunResults
            runId={selectedRunId}
            apiClient={apiClient}
          />
        )
      default:
        return (
          <PressPlanner
            apiClient={apiClient}
            aiAvailable={aiAvailable}
            onRunComplete={handleNewRun}
          />
        )
    }
  }, [currentView, selectedRunId, aiAvailable, handleSelectRun, handleNewRun])

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <div className="header-title">
            <h1>🔬 Evidence Assistant</h1>
            <p>AI-Powered Systematic Literature Review Platform</p>
          </div>
          <nav className="header-nav">
            <button
              className={`nav-button ${currentView === 'planner' ? 'active' : ''}`}
              onClick={() => handleViewChange('planner')}
            >
              New Review
            </button>
            <button
              className={`nav-button ${currentView === 'history' ? 'active' : ''}`}
              onClick={() => handleViewChange('history')}
            >
              Review History
            </button>
            {currentView === 'results' && (
              <button
                className="nav-button active"
                disabled
              >
                Results
              </button>
            )}
          </nav>
        </div>
      </header>
      
      <main className="app-main">
        {currentViewComponent}
      </main>
      
      <footer className="app-footer">
        <p>Systematic Review • PRESS Planning • Quality Assessment</p>
      </footer>
    </div>
  )
}

export default App
