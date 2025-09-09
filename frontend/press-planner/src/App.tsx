import { useState, useEffect } from 'react'
import './App.css'
import { PressPlanner } from './components/PressPlanner'
import { RunHistory } from './components/RunHistory'
import { RunResults } from './components/RunResults'
import { ApiClient } from './services/apiClient'

const apiClient = new ApiClient()

type AppView = 'planner' | 'history' | 'results'

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

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading Evidence Assistant...</p>
      </div>
    )
  }

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId)
    setCurrentView('results')
  }

  const handleNewRun = (runId: string, runData?: any) => {
    setSelectedRunId(runId)
    setCurrentView('results')
  }

  const renderCurrentView = () => {
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
          setCurrentView('planner')
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
  }

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
              onClick={() => setCurrentView('planner')}
            >
              New Review
            </button>
            <button 
              className={`nav-button ${currentView === 'history' ? 'active' : ''}`}
              onClick={() => setCurrentView('history')}
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
        {renderCurrentView()}
      </main>
      
      <footer className="app-footer">
        <p>Systematic Review • PRESS Planning • Quality Assessment</p>
      </footer>
    </div>
  )
}

export default App
