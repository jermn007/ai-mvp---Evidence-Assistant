import { useEffect, useCallback, useRef } from 'react'

interface PerformanceMetrics {
  componentRenderTime: number
  apiResponseTime: number
  memoryUsage: number
  timestamp: number
}

/**
 * Custom hook for monitoring component performance
 * Tracks render times, API response times, and memory usage
 */
export function usePerformanceMonitor(componentName: string) {
  const renderStartTime = useRef<number>(performance.now())
  const metricsRef = useRef<PerformanceMetrics[]>([])

  // Track component render performance
  useEffect(() => {
    const renderEndTime = performance.now()
    const renderTime = renderEndTime - renderStartTime.current

    const metrics: PerformanceMetrics = {
      componentRenderTime: renderTime,
      apiResponseTime: 0, // Will be updated by API calls
      memoryUsage: (performance as any).memory?.usedJSHeapSize || 0,
      timestamp: Date.now()
    }

    metricsRef.current.push(metrics)

    // Keep only last 50 metrics to prevent memory leaks
    if (metricsRef.current.length > 50) {
      metricsRef.current = metricsRef.current.slice(-50)
    }

    // Log performance warnings in development
    if (__DEV__ && renderTime > 16) { // 60fps = 16.67ms per frame
      console.warn(
        `⚠️ Performance: ${componentName} render took ${renderTime.toFixed(2)}ms (> 16ms)`
      )
    }

    // Reset for next render
    renderStartTime.current = performance.now()
  })

  // Track API response times
  const trackApiCall = useCallback(async <T>(
    apiCall: Promise<T>,
    operationName: string
  ): Promise<T> => {
    const startTime = performance.now()

    try {
      const result = await apiCall
      const endTime = performance.now()
      const responseTime = endTime - startTime

      // Update latest metrics with API response time
      if (metricsRef.current.length > 0) {
        metricsRef.current[metricsRef.current.length - 1].apiResponseTime = responseTime
      }

      // Log slow API calls in development
      if (__DEV__ && responseTime > 1000) { // > 1 second
        console.warn(
          `⚠️ Performance: ${operationName} API call took ${responseTime.toFixed(2)}ms (> 1s)`
        )
      }

      return result
    } catch (error) {
      const endTime = performance.now()
      const responseTime = endTime - startTime

      if (__DEV__) {
        console.error(
          `❌ Performance: ${operationName} API call failed after ${responseTime.toFixed(2)}ms`,
          error
        )
      }

      throw error
    }
  }, [])

  // Get performance summary
  const getPerformanceSummary = useCallback(() => {
    if (metricsRef.current.length === 0) return null

    const recentMetrics = metricsRef.current.slice(-10) // Last 10 renders

    const avgRenderTime = recentMetrics.reduce(
      (sum, metric) => sum + metric.componentRenderTime, 0
    ) / recentMetrics.length

    const avgApiTime = recentMetrics
      .filter(metric => metric.apiResponseTime > 0)
      .reduce((sum, metric) => sum + metric.apiResponseTime, 0) /
      recentMetrics.filter(metric => metric.apiResponseTime > 0).length || 0

    const currentMemory = recentMetrics[recentMetrics.length - 1]?.memoryUsage || 0

    return {
      componentName,
      averageRenderTime: avgRenderTime,
      averageApiResponseTime: avgApiTime,
      currentMemoryUsage: currentMemory,
      totalRenders: metricsRef.current.length,
      timestamp: Date.now()
    }
  }, [componentName])

  // Log performance summary on unmount in development
  useEffect(() => {
    return () => {
      if (__DEV__) {
        const summary = getPerformanceSummary()
        if (summary) {
          console.group(`📊 Performance Summary: ${componentName}`)
          console.log(`Average Render Time: ${summary.averageRenderTime.toFixed(2)}ms`)
          console.log(`Average API Time: ${summary.averageApiResponseTime.toFixed(2)}ms`)
          console.log(`Memory Usage: ${(summary.currentMemoryUsage / 1024 / 1024).toFixed(2)}MB`)
          console.log(`Total Renders: ${summary.totalRenders}`)
          console.groupEnd()
        }
      }
    }
  }, [componentName, getPerformanceSummary])

  return {
    trackApiCall,
    getPerformanceSummary,
    metricsCount: metricsRef.current.length
  }
}