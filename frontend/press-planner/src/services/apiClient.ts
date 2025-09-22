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

export interface LICOInsights {
  learner_insights: string
  intervention_insights: string
  context_insights: string
  outcome_insights: string
}

export interface EvidenceSupport {
  finding: string
  supporting_quotes: string[]
  source_studies: string[]
  strength_rating: string
}

export interface ResearchSynthesis {
  executive_summary: string
  research_question_answer: string
  lico_insights: LICOInsights
  evidence_strength: string
  confidence_level: string
  key_recommendations: string[]
  knowledge_gaps: string[]
  methodological_quality: string
  future_research_directions: string[]
  supporting_evidence: EvidenceSupport[]
  full_text_availability: Record<string, boolean> // Keyed by record_id
}

export class ApiClient {
  private baseUrl: string
  private abortControllers: Map<string, AbortController> = new Map()
  private requestCache: Map<string, { data: any; timestamp: number; hits: number; lastAccess: number }> = new Map()
  private persistentCache: Map<string, { data: any; timestamp: number }> = new Map()
  private pendingRequests: Map<string, Promise<any>> = new Map()
  private readonly CACHE_TTL = 5 * 60 * 1000 // 5 minutes cache
  private readonly PERSISTENT_CACHE_TTL = 30 * 60 * 1000 // 30 minutes for frequently accessed data
  private readonly LONG_CACHE_TTL = 2 * 60 * 60 * 1000 // 2 hours for stable data
  private cacheCleanupInterval: number | null = null

  constructor(baseUrl: string = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.initializeCacheCleanup()
    this.loadPersistentCache()
  }

  private getCacheKey(endpoint: string, options?: RequestInit): string {
    const method = options?.method || 'GET'
    const body = options?.body ? JSON.stringify(JSON.parse(options.body as string)) : '{}'
    const params = endpoint.includes('?') ? endpoint.split('?')[1] : ''
    return `${method}:${endpoint.split('?')[0]}:${body}:${params}`
  }

  private getRequestKey(endpoint: string, options?: RequestInit): string {
    // For GET requests, use stable key to allow proper request deduplication
    // For POST/PUT/DELETE, use timestamp to allow concurrent operations
    const baseKey = `${endpoint}:${JSON.stringify(options?.body || {})}`
    const method = options?.method || 'GET'

    if (method === 'GET') {
      return baseKey
    } else {
      return `${baseKey}:${Date.now()}`
    }
  }

  private getFromCache<T>(key: string): T | null {
    // Check memory cache first
    const cached = this.requestCache.get(key)
    if (cached && Date.now() - cached.timestamp < this.getCacheTTL(key)) {
      cached.hits++
      cached.lastAccess = Date.now()
      return cached.data
    }

    // Check persistent cache for frequently accessed data
    const persistent = this.persistentCache.get(key)
    if (persistent && Date.now() - persistent.timestamp < this.PERSISTENT_CACHE_TTL) {
      // Promote to memory cache
      this.setCache(key, persistent.data)
      return persistent.data
    }

    return null
  }

  private setCache<T>(key: string, data: T): void {
    const now = Date.now()
    this.requestCache.set(key, {
      data,
      timestamp: now,
      hits: 1,
      lastAccess: now
    })

    // For certain endpoints, also cache persistently
    if (this.shouldPersistCache(key)) {
      this.persistentCache.set(key, { data, timestamp: now })
      this.savePersistentCache()
    }
  }

  private createAbortController(key: string, options?: RequestInit): AbortController {
    const method = options?.method || 'GET'

    // For GET requests, be more careful about canceling existing requests
    // Only cancel if the request is actually the same endpoint
    const existing = this.abortControllers.get(key)
    if (existing && !existing.signal.aborted) {
      // For GET requests, only abort if it's been running for more than 30 seconds
      // For POST/PUT/DELETE, abort immediately to prevent conflicts
      if (method !== 'GET') {
        existing.abort()
      }
    }

    const controller = new AbortController()
    this.abortControllers.set(key, controller)
    return controller
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const cacheKey = this.getCacheKey(endpoint, options)
    const requestKey = this.getRequestKey(endpoint, options)

    // Check cache for GET requests
    if (!options?.method || options.method === 'GET') {
      const cached = this.getFromCache<T>(cacheKey)
      if (cached) {
        // Trigger background refresh for stale data
        this.scheduleBackgroundRefresh(endpoint, options, cacheKey)
        return cached
      }
    }

    // Check for pending requests to avoid duplicates
    const pendingKey = `${requestKey}`
    if (this.pendingRequests.has(pendingKey)) {
      return this.pendingRequests.get(pendingKey) as Promise<T>
    }

    const url = `${this.baseUrl}${endpoint}`
    const controller = this.createAbortController(requestKey, options)

    const requestPromise = this.executeRequest<T>(url, options, controller)
    this.pendingRequests.set(pendingKey, requestPromise)

    try {
      const data = await requestPromise

      // Cache successful GET requests
      if (!options?.method || options.method === 'GET') {
        this.setCache(cacheKey, data)
      }

      // Trigger prefetching for related data
      this.triggerPrefetch(endpoint, data)

      return data
    } finally {
      this.abortControllers.delete(requestKey)
      this.pendingRequests.delete(pendingKey)
    }
  }

  private async executeRequest<T>(url: string, options: RequestInit | undefined, controller: AbortController): Promise<T> {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      signal: controller.signal,
      ...options,
    })

    if (!response.ok) {
      const errorText = await response.text()

      // Enhanced error handling for different response codes
      let errorMessage = errorText
      let errorData: any = null

      try {
        errorData = JSON.parse(errorText)
      } catch {
        // Not JSON, use text as-is
      }

      // Handle rate limiting (429)
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After')
        const retrySeconds = retryAfter ? parseInt(retryAfter, 10) : 60

        if (errorData?.detail) {
          errorMessage = `Rate limited: ${errorData.detail}. Please wait ${retrySeconds} seconds before trying again.`
        } else {
          errorMessage = `Too many requests. Please wait ${retrySeconds} seconds before trying again.`
        }

        const error = new Error(errorMessage) as any
        error.status = 429
        error.retryAfter = retrySeconds
        error.isRateLimit = true
        throw error
      }

      // Handle validation errors (422)
      if (response.status === 422) {
        if (errorData?.detail) {
          // Pydantic validation error format
          if (Array.isArray(errorData.detail)) {
            const validationErrors = errorData.detail.map((err: any) => {
              const field = err.loc ? err.loc.join('.') : 'unknown'
              return `${field}: ${err.msg}`
            }).join('; ')
            errorMessage = `Validation error: ${validationErrors}`
          } else {
            errorMessage = `Validation error: ${errorData.detail}`
          }
        } else {
          errorMessage = 'Invalid input data'
        }

        const error = new Error(errorMessage) as any
        error.status = 422
        error.isValidation = true
        error.validationDetails = errorData?.detail
        throw error
      }

      // Handle authentication errors (401, 403)
      if (response.status === 401 || response.status === 403) {
        errorMessage = 'Authentication required or access denied'
        const error = new Error(errorMessage) as any
        error.status = response.status
        error.isAuth = true
        throw error
      }

      // Handle server errors (5xx)
      if (response.status >= 500) {
        errorMessage = errorData?.detail || 'Server error occurred. Please try again later.'
        const error = new Error(errorMessage) as any
        error.status = response.status
        error.isServerError = true
        throw error
      }

      // Generic error
      const error = new Error(`API Error (${response.status}): ${errorMessage}`) as any
      error.status = response.status
      error.responseData = errorData
      throw error
    }

    return response.json()
  }

  // Cancel all pending requests
  cancelAllRequests(): void {
    this.abortControllers.forEach(controller => controller.abort())
    this.abortControllers.clear()
  }

  // Enhanced cache management methods
  private getCacheTTL(key: string): number {
    // Different TTL for different types of requests
    if (key.includes('/ai/status') || key.includes('/health')) {
      return this.LONG_CACHE_TTL // Status endpoints change rarely
    }
    if (key.includes('/runs/') && key.includes('/summary')) {
      return this.PERSISTENT_CACHE_TTL // Run summaries are relatively stable
    }
    if (key.includes('.page.json')) {
      return this.CACHE_TTL // Paginated data has shorter TTL
    }
    return this.CACHE_TTL
  }

  private shouldPersistCache(key: string): boolean {
    // Persist cache for certain stable endpoints
    return (
      key.includes('/runs/') ||
      key.includes('/ai/status') ||
      key.includes('/health') ||
      key.includes('/summary')
    )
  }

  private initializeCacheCleanup(): void {
    // Clean cache every 10 minutes
    this.cacheCleanupInterval = setInterval(() => {
      this.cleanupExpiredCache()
    }, 10 * 60 * 1000) as any
  }

  private cleanupExpiredCache(): void {
    const now = Date.now()

    // Clean memory cache
    for (const [key, cached] of this.requestCache.entries()) {
      if (now - cached.timestamp > this.getCacheTTL(key)) {
        this.requestCache.delete(key)
      }
    }

    // Clean persistent cache
    for (const [key, cached] of this.persistentCache.entries()) {
      if (now - cached.timestamp > this.PERSISTENT_CACHE_TTL) {
        this.persistentCache.delete(key)
      }
    }
  }

  private loadPersistentCache(): void {
    try {
      const stored = localStorage.getItem('apiClient:persistentCache')
      if (stored) {
        const parsed = JSON.parse(stored)
        this.persistentCache = new Map(Object.entries(parsed))
      }
    } catch (error) {
      console.warn('Failed to load persistent cache:', error)
    }
  }

  private savePersistentCache(): void {
    try {
      const data = Object.fromEntries(this.persistentCache.entries())
      localStorage.setItem('apiClient:persistentCache', JSON.stringify(data))
    } catch (error) {
      console.warn('Failed to save persistent cache:', error)
    }
  }

  private scheduleBackgroundRefresh(endpoint: string, options: RequestInit | undefined, cacheKey: string): void {
    // Refresh stale cache in background for better UX
    const cached = this.requestCache.get(cacheKey)
    if (cached && Date.now() - cached.timestamp > this.getCacheTTL(cacheKey) * 0.8) {
      // Refresh when cache is 80% expired
      setTimeout(async () => {
        try {
          await this.executeRequest(
            `${this.baseUrl}${endpoint}`,
            options,
            new AbortController()
          ).then(data => this.setCache(cacheKey, data))
        } catch (error) {
          // Silent background refresh failure
        }
      }, 100)
    }
  }

  private triggerPrefetch(endpoint: string, data: any): void {
    // Prefetch related data based on current request
    if (endpoint.includes('/runs.page.json') && data.items) {
      // Prefetch first few run summaries
      data.items.slice(0, 3).forEach((run: any) => {
        if (run.id) {
          setTimeout(() => {
            this.getRunSummary(run.id).catch(() => {})
          }, 500)
        }
      })
    }

    if (endpoint.includes('/runs/') && endpoint.includes('/summary') && data.run?.id) {
      // Prefetch records when summary is loaded
      setTimeout(() => {
        this.getRecordsWithAppraisals(data.run.id, { limit: 20, offset: 0 }).catch(() => {})
      }, 1000)
    }
  }

  // Enhanced cache management
  clearCache(): void {
    this.requestCache.clear()
    this.persistentCache.clear()
    this.pendingRequests.clear()
    localStorage.removeItem('apiClient:persistentCache')
  }

  getCacheStats(): { memory: number; persistent: number; pending: number } {
    return {
      memory: this.requestCache.size,
      persistent: this.persistentCache.size,
      pending: this.pendingRequests.size
    }
  }

  // Cache invalidation for specific patterns
  invalidateCache(pattern?: string): void {
    if (!pattern) {
      this.clearCache()
      return
    }

    for (const key of this.requestCache.keys()) {
      if (key.includes(pattern)) {
        this.requestCache.delete(key)
      }
    }

    for (const key of this.persistentCache.keys()) {
      if (key.includes(pattern)) {
        this.persistentCache.delete(key)
      }
    }
  }

  // Cleanup on destroy
  destroy(): void {
    if (this.cacheCleanupInterval) {
      clearInterval(this.cacheCleanupInterval)
    }
    this.cancelAllRequests()
    this.clearCache()
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

  async previewPressStrategy(lico: LICO): Promise<{
    lico_input: LICO
    extracted_terms: Record<string, string[]>
    merged_terms: Record<string, {
      user_extracted: string[]
      yaml_mesh: string[]
      yaml_text: string[]
      final_mesh: string[]
      final_text: string[]
    }>
    sample_strategy: any
    message: string
  }> {
    return this.request('/press/plan/preview', {
      method: 'POST',
      body: JSON.stringify({ lico }),
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
  async runWithPlan(
    plan: PressPlan,
    options?: {
      sources?: string[]
      searchMode?: 'quick' | 'standard' | 'comprehensive'
      maxResultsPerSource?: number
    }
  ): Promise<any> {
    const payload: Record<string, any> = {
      plan,
      sources: options?.sources || ['PubMed', 'Crossref', 'ERIC', 'SemanticScholar', 'GoogleScholar', 'arXiv']
    }

    if (options?.searchMode) {
      const normalized = options.searchMode.toString().toLowerCase()
      const label = normalized.charAt(0).toUpperCase() + normalized.slice(1)
      payload.search_mode = label
    }

    if (typeof options?.maxResultsPerSource === 'number') {
      payload.max_results_per_source = options.maxResultsPerSource
    }

    return this.request('/run/press', {
      method: 'POST',
      body: JSON.stringify(payload)
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

  async getScreeningsWithRecords(runId: string, params?: Record<string, any>): Promise<any> {
    const queryString = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request(`/runs/${runId}/screenings_with_records.page.json${queryString}`)
  }

  // Get detailed multi-method appraisals
  async getDetailedAppraisals(runId: string, params?: Record<string, any>): Promise<any> {
    const queryString = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request(`/runs/${runId}/detailed_appraisals.json${queryString}`)
  }

  // Get available appraisal methodologies
  async getAppraisalMethodologies(): Promise<any> {
    return this.request('/appraisal/methodologies')
  }

  // AI Research Synthesis
  async generateResearchSynthesis(runId: string, options?: {
    research_question?: string
    focus_areas?: string[]
    max_studies?: number
  }): Promise<ResearchSynthesis> {
    // Use real AI synthesis endpoint with actual research data
    return this.request<ResearchSynthesis>(`/test/real-synthesis/${runId}`, {
      method: 'POST',
      body: JSON.stringify(options || {})
    })
  }
}

// Helper type for template response - exported for use in components
export interface TemplateResponse {
  suggested_template: string
  available_templates: string[]
  reasoning: string
  error?: string
}