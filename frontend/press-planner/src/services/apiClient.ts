// API client for Evidence Assistant backend

export interface LICO {
  learner: string
  intervention: string
  context: string
  outcome: string
}

export interface LICOEnhancement {
  learner_suggestions: string[]
  intervention_suggestions: string[]
  context_suggestions: string[]
  outcome_suggestions: string[]
  mesh_suggestions: Record<string, string[]>
  template_recommendation: string
  explanation: string
}

export interface PressStrategyAnalysis {
  completeness_score: number
  balance_assessment: string
  suggestions: string[]
  missing_components: string[]
  estimated_precision: string
  estimated_recall: string
}


export interface AiStatus {
  available: boolean
  model?: string
  features: string[]
}

export interface PressPlan {
  question_lico: LICO
  strategies: Record<string, any>
  checklist: Record<string, any>
}

export interface AiEnhancedPlan {
  base_plan: PressPlan
  ai_enhancement?: LICOEnhancement
  strategy_analysis?: PressStrategyAnalysis
  ai_available: boolean
  ai_error?: string
}

export class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`API Error (${response.status}): ${errorText}`)
    }

    return response.json()
  }

  // AI Status and Health
  async checkAiStatus(): Promise<AiStatus> {
    return this.request<AiStatus>('/ai/status')
  }

  // Template Selection
  async suggestTemplate(lico: LICO): Promise<TemplateResponse> {
    return this.request<TemplateResponse>('/ai/suggest-template', {
      method: 'POST',
      body: JSON.stringify(lico),
    })
  }

  // LICO Enhancement
  async enhanceLico(lico: LICO, researchDomain?: string): Promise<LICOEnhancement> {
    return this.request<LICOEnhancement>('/ai/enhance-lico', {
      method: 'POST',
      body: JSON.stringify({
        lico,
        research_domain: researchDomain,
      }),
    })
  }

  // PRESS Planning
  async createPressPlan(params: {
    lico: LICO
    template?: string
    useStock?: boolean
    enableAi?: boolean
    researchDomain?: string
  }): Promise<PressPlan> {
    const endpoint = params.enableAi ? '/press/plan/ai-enhanced' : '/press/plan'
    
    return this.request<PressPlan | AiEnhancedPlan>(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        lico: params.lico,
        template: params.template || 'education',
        use_stock: params.useStock !== false,
        enable_ai: params.enableAi || false,
        research_domain: params.researchDomain,
      }),
    })
  }

  // Strategy Analysis
  async analyzeStrategy(strategyLines: Array<{type: string, text: string}>): Promise<PressStrategyAnalysis> {
    return this.request<PressStrategyAnalysis>('/ai/analyze-strategy', {
      method: 'POST',
      body: JSON.stringify({
        strategy_lines: strategyLines,
      }),
    })
  }

  // Query Generation
  async generateQueries(plan: PressPlan): Promise<{query_pubmed: string, query_generic: string, years: string}> {
    return this.request('/press/plan/queries', {
      method: 'POST',
      body: JSON.stringify({plan}),
    })
  }

  // Research Question ↔ LICO Conversion
  async generateResearchQuestion(lico: LICO): Promise<{question: string}> {
    return this.request('/ai/generate-question', {
      method: 'POST',
      body: JSON.stringify({lico}),
    })
  }

  async extractLicoFromQuestion(question: string): Promise<{lico: LICO}> {
    return this.request('/ai/extract-lico', {
      method: 'POST',
      body: JSON.stringify({question}),
    })
  }

  async enhanceResearchQuestion(question: string): Promise<{enhanced_question: string}> {
    return this.request('/ai/enhance-question', {
      method: 'POST',
      body: JSON.stringify({question}),
    })
  }

  async assessStudyRelevance(params: {
    title: string
    abstract?: string
    inclusion_criteria: string[]
    exclusion_criteria: string[]
    research_question?: string
  }): Promise<any> {
    return this.request('/ai/assess-relevance', {
      method: 'POST',
      body: JSON.stringify(params)
    })
  }

  // Runs and Results
  async runWithPlan(plan: PressPlan, sources?: string[]): Promise<any> {
    return this.request('/run/press', {
      method: 'POST',
      body: JSON.stringify({
        plan,
        sources: sources || ['PubMed', 'Crossref', 'ERIC', 'SemanticScholar', 'GoogleScholar', 'arXiv']
      })
    })
  }

  async getRuns(limit: number = 20, offset: number = 0): Promise<{items: any[], total: number}> {
    return this.request(`/runs.page.json?limit=${limit}&offset=${offset}`)
  }

  async getRunSummary(runId: string): Promise<any> {
    return this.request(`/runs/${runId}/summary.json`)
  }

  async getRecordsWithAppraisals(runId: string, params?: Record<string, any>): Promise<any> {
    const queryString = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request(`/runs/${runId}/records_with_appraisals.page.json${queryString}`)
  }
}

// Helper type for template response - exported for use in components
export interface TemplateResponse {
  suggested_template: string
  available_templates: string[]
  reasoning: string
  error?: string
}