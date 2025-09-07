import { useState, useEffect } from 'react'
import './App.css'
import { PressPlanner } from './components/PressPlanner'
import { ApiClient } from './services/apiClient'

const apiClient = new ApiClient()

function App() {
  const [aiAvailable, setAiAvailable] = useState<boolean>(false)
  const [loading, setLoading] = useState(true)

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

  return (
    <div className="app">
      <header className="app-header">
        <h1>🔬 Evidence Assistant</h1>
        <p>AI-Powered Systematic Literature Review Platform</p>
      </header>
      
      <main className="app-main">
        <PressPlanner 
          apiClient={apiClient} 
          aiAvailable={aiAvailable} 
        />
      </main>
      
      <footer className="app-footer">
        <p>Systematic Review • PRESS Planning • Quality Assessment</p>
      </footer>
    </div>
  )
}

export default App
