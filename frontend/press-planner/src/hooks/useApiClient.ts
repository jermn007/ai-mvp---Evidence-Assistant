import { useCallback, useEffect, useMemo } from 'react'
import { ApiClient } from '../services/apiClient'

// Singleton API client instance for performance
let apiClientInstance: ApiClient | null = null

/**
 * Custom hook for managing API client with optimizations
 * - Provides singleton instance to prevent unnecessary recreations
 * - Includes request cancellation on unmount
 * - Memoizes common operations
 */
export function useApiClient(baseUrl?: string) {
  // Create or reuse singleton instance
  const apiClient = useMemo(() => {
    if (!apiClientInstance || (baseUrl && apiClientInstance['baseUrl'] !== baseUrl)) {
      apiClientInstance = new ApiClient(baseUrl)
    }
    return apiClientInstance
  }, [baseUrl])

  // Cleanup effect to cancel requests on unmount
  useEffect(() => {
    return () => {
      apiClient.cancelAllRequests()
    }
  }, [apiClient])

  // Memoized common operations
  const operations = useMemo(() => ({
    // Health checks
    checkAiStatus: () => apiClient.checkAiStatus(),

    // LICO operations
    enhanceLico: (lico: any, domain?: string) =>
      apiClient.enhanceLico(lico, domain),

    // PRESS planning
    createPressPlan: (params: any) =>
      apiClient.createPressPlan(params),

    // Workflow execution
    runWithPlan: (plan: any, options?: { sources?: string[]; searchMode?: string; maxResultsPerSource?: number }) =>
      apiClient.runWithPlan(plan, options),

    // Results retrieval
    getRunSummary: (runId: string) =>
      apiClient.getRunSummary(runId),

    getRuns: (limit?: number, offset?: number) =>
      apiClient.getRuns(limit, offset),
  }), [apiClient])

  // Cleanup function for manual use
  const cleanup = useCallback(() => {
    apiClient.cancelAllRequests()
    apiClient.clearCache()
  }, [apiClient])

  return {
    apiClient,
    operations,
    cleanup
  }
}

/**
 * Hook for managing API request state with automatic cleanup
 */
export function useApiRequest<T>(
  requestFn: () => Promise<T>,
  dependencies: any[] = []
) {
  const { apiClient } = useApiClient()

  const execute = useCallback(async () => {
    try {
      return await requestFn()
    } catch (error) {
      // Re-throw for component error handling
      throw error
    }
  }, [requestFn])

  useEffect(() => {
    return () => {
      apiClient.cancelAllRequests()
    }
  }, dependencies)

  return execute
}