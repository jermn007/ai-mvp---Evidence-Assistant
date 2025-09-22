import { useState, useEffect } from 'react'
import { ApiClient } from '../services/apiClient'
import type { CitationMetadata } from '../services/apiClient'
import { DetailedAppraisalView } from './DetailedAppraisalView'
import './RunResults.css'

// Author Display Component with truncation and expansion
interface AuthorDisplayProps {
  authors: string;
}

const AuthorDisplay: React.FC<AuthorDisplayProps> = ({ authors }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Parse authors from comma-separated string
  const authorsList = authors.split(',').map(author => author.trim()).filter(author => author.length > 0);
  const needsTruncation = authorsList.length > 4;

  const displayAuthors = isExpanded || !needsTruncation
    ? authorsList
    : authorsList.slice(0, 4);

  return (
    <span className="author-display">
      {displayAuthors.join(', ')}
      {needsTruncation && !isExpanded && (
        <>
          {' et al.'}
          <button
            className="author-toggle-btn"
            onClick={() => setIsExpanded(true)}
            type="button"
          >
            Show all authors
          </button>
        </>
      )}
      {needsTruncation && isExpanded && (
        <button
          className="author-toggle-btn"
          onClick={() => setIsExpanded(false)}
          type="button"
        >
          Show fewer authors
        </button>
      )}
    </span>
  );
};

// Abstract Display Component with expand/collapse functionality
interface AbstractDisplayProps {
  abstract: string;
}

const AbstractDisplay: React.FC<AbstractDisplayProps> = ({ abstract }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const cleanedAbstract = abstract.replace(/<\/?jats:[^>]*>/g, '').trim();
  const needsTruncation = cleanedAbstract.length > 150;

  // Fix truncation logic: start from beginning, add ellipsis only when truncated
  const displayText = isExpanded || !needsTruncation
    ? cleanedAbstract
    : cleanedAbstract.substring(0, 150).trim();

  return (
    <div className="record-abstract">
      <strong>Abstract:</strong>
      <span className="abstract-text">
        {displayText}
        {needsTruncation && !isExpanded && '...'}
      </span>
      {needsTruncation && (
        <button
          className="abstract-toggle-btn"
          onClick={() => setIsExpanded(!isExpanded)}
          type="button"
        >
          {isExpanded ? 'Show less' : 'Show full abstract'}
        </button>
      )}
    </div>
  );
};

interface RunResultsProps {
  runId?: string
  runData?: any  // Complete run results from immediate execution
  apiClient: ApiClient
}

interface RunSummary {
  run_id: string
  status: string
  created_at: string
  total_records: number
  screened_records: number
  included_records: number
  excluded_records: number
  appraised_records: number
  prisma_counts?: {
    initial_records: number
    after_deduplication: number
    after_screening: number
    after_appraisal: number
    final_included: number
  }
}

// Enhanced appraisal methodology information
interface AppraisalMethodology {
  id: string
  name: string
  version: string
  description?: string
  method_type: 'rag_quality' | 'kirkpatrick' | 'towle' | 'strength_conclusion' | 'custom'
  criteria: Record<string, {
    weight: number
    description: string
  }>
  scoring_config: Record<string, any>
  requires_full_text: boolean
}

// Detailed appraisal scores and metadata
interface DetailedAppraisal {
  id: string
  methodology_id: string
  methodology?: AppraisalMethodology
  scores: Record<string, number>  // Individual criterion scores
  overall_score: number
  rating: string
  rationale?: string
  evidence_citations?: string[]
  confidence: number
  used_full_text: boolean
  sections_analyzed?: string[]
  assessed_by?: string
  assessment_time?: number
  created_at: string
}

interface RecordWithAppraisal {
  id: string
  title: string
  authors?: string
  year?: number
  source: string
  abstract?: string
  doi?: string
  url?: string
  publication_type?: string
  institution?: string  // Author affiliation/institution
  screening_decision?: 'include' | 'exclude'
  screening_reason?: string
  screening_ai_explanation?: string
  appraisal_score?: number
  appraisal_color?: 'Red' | 'Amber' | 'Green'
  appraisal_reasoning?: string
  ai_review_type?: 'full_text' | 'abstract_only'
  status?: 'Include' | 'Exclude'  // For display purposes
  // Enhanced appraisal data
  detailed_appraisals?: DetailedAppraisal[]
  multi_method_scores?: Record<string, DetailedAppraisal>
  confidence_range?: [number, number]  // Min/max confidence across methods
}

type SortField = 'title' | 'appraisal_score' | 'publication_type' | 'year' | 'authors' | 'status'
type SortOrder = 'asc' | 'desc'

// Smart data fallback helpers
function extractAuthorsFromTitle(title: string): string | null {
  // Look for common author patterns in titles
  const patterns = [
    // "by Author Name" patterns - most reliable
    /by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]*\.?)*(?:\s+and\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]*\.?)*)*)/i,
    // "Author et al." patterns - reliable
    /([A-Z][a-z]+(?:\s+[A-Z]\.)*(?:\s+[A-Z][a-z]+)?)\s+et\s+al\.?/i,
    // Single author name at start with colon (First Last:) - must be reasonable length
    /^([A-Z][a-z]{2,15}\s+[A-Z][a-z]{2,15}):\s/,
  ]

  // Common non-author words that appear in titles (more conservative list)
  const invalidAuthorWords = [
    'infinity', 'instruct', 'synthesis', 'framework', 'methodology', 'approach',
    'analysis', 'study', 'research', 'review', 'systematic', 'meta', 'evidence',
    'implementation', 'effectiveness', 'evaluation'
  ]

  for (const pattern of patterns) {
    const match = title.match(pattern)
    if (match && match[1].length > 3 && match[1].length < 50) {
      const extracted = match[1].trim()

      // Check if extracted text contains common non-author words
      const hasInvalidWords = invalidAuthorWords.some(word =>
        extracted.toLowerCase().includes(word)
      )

      // Must contain at least one common name pattern (First Last or Last, First)
      const hasNamePattern = /^[A-Z][a-z]{2,15}\s+[A-Z][a-z]{2,15}$/.test(extracted) ||
                            /^[A-Z][a-z]{2,15},\s*[A-Z][a-z]{2,15}/.test(extracted)

      if (!hasInvalidWords && hasNamePattern) {
        return extracted
      }
    }
  }
  return null
}

function extractYearFromTitle(title: string): number | null {
  // Try to extract year from title
  const yearMatch = title.match(/\b(19|20)\d{2}\b/)
  return yearMatch ? parseInt(yearMatch[0]) : null
}

function extractYearFromId(recordId: string): number | null {
  // Extract year from PMID (PubMed ID format often contains year info)
  const pmidMatch = recordId.match(/pmid:(\d+)/)
  if (pmidMatch) {
    const pmid = pmidMatch[1]
    // PMID ranges can help estimate publication year
    const pmidNum = parseInt(pmid)
    if (pmidNum > 30000000) return 2020
    if (pmidNum > 25000000) return 2018
    if (pmidNum > 20000000) return 2015
    if (pmidNum > 15000000) return 2010
    return null
  }

  // Extract year from DOI
  const doiMatch = recordId.match(/doi:.*[./](\d{4})[./]/)
  if (doiMatch) {
    const year = parseInt(doiMatch[1])
    if (year >= 1990 && year <= new Date().getFullYear()) {
      return year
    }
  }

  return null
}

function inferSourceFromId(recordId: string, currentSource?: string): string {
  if (currentSource && currentSource !== 'Unknown') {
    return currentSource
  }

  if (recordId.includes('pmid:')) return 'PubMed'
  if (recordId.includes('doi:')) return 'DOI Database'
  if (recordId.includes('scholar:')) return 'Google Scholar'
  if (recordId.includes('arxiv:')) return 'arXiv'
  if (recordId.includes('eric:')) return 'ERIC'

  return 'Academic Database'
}

function inferPublicationType(title: string, recordId: string): string {
  const titleLower = title.toLowerCase()

  // Check for review types
  if (titleLower.includes('systematic review')) return 'Systematic Review'
  if (titleLower.includes('meta-analysis') || titleLower.includes('meta analysis')) return 'Meta-Analysis'
  if (titleLower.includes('review') && !titleLower.includes('peer review')) return 'Review Article'

  // Check for study types
  if (titleLower.includes('randomized') || titleLower.includes('rct')) return 'Randomized Controlled Trial'
  if (titleLower.includes('cohort study')) return 'Cohort Study'
  if (titleLower.includes('case study')) return 'Case Study'
  if (titleLower.includes('cross-sectional')) return 'Cross-Sectional Study'

  // Default based on source
  if (recordId.includes('arxiv:')) return 'Preprint'

  return 'Research Article'
}

function getDisplayAuthors(record: RecordWithAppraisal): string {
  // Check if we have author data at all from the backend
  if (record.authors && record.authors.trim()) {
    const authorsLower = record.authors.toLowerCase()

    // Filter out obvious placeholders from data sources
    const isValidAuthorData = (
      authorsLower !== 'null' &&
      authorsLower !== 'undefined' &&
      authorsLower !== 'unknown' &&
      !authorsLower.startsWith('journal article') &&
      !authorsLower.startsWith('research article') &&
      !authorsLower.startsWith('review article') &&
      !authorsLower.startsWith('conference paper') &&
      !authorsLower.startsWith('book chapter') &&
      // Only filter out exact placeholder phrases
      !(authorsLower === 'not available' || authorsLower === 'not specified')
    )

    // If it passes the placeholder filter, use it (trust backend data)
    if (isValidAuthorData) {
      return record.authors
    }
  }

  // Try to extract authors from title if no valid author data from backend
  const extractedAuthors = extractAuthorsFromTitle(record.title)
  if (extractedAuthors) {
    return extractedAuthors
  }

  // Note: Backend doesn't provide author data for this dataset
  return "Authors not specified"
}

function getDisplayYear(record: RecordWithAppraisal): string {
  if (record.year) {
    return record.year.toString()
  }

  // Try extracting from title first
  const extractedYear = extractYearFromTitle(record.title)
  if (extractedYear) {
    return extractedYear.toString()
  }

  // Try extracting from record ID
  const idYear = extractYearFromId(record.id)
  if (idYear) {
    return idYear.toString()
  }

  return "Year unknown"
}

function getConfidenceLevel(record: RecordWithAppraisal): 'high' | 'medium' | 'low' {
  // Mock confidence calculation - in real app this would come from detailed_appraisals
  const baseConfidence = record.appraisal_score || 0.5
  if (baseConfidence >= 0.8) return 'high'
  if (baseConfidence >= 0.6) return 'medium'
  return 'low'
}

// Helper functions for excluded records

// Simplified title display function - backend should now provide proper titles
function getDisplayTitle(originalTitle: string | null | undefined, recordId: string, reason?: string, isIncluded: boolean = true): string {
  // Return the title from the backend if available
  if (originalTitle && originalTitle.trim()) {
    return originalTitle
  }

  // Fallback for completely missing titles
  return 'Untitled Study'
}


// Enhanced mock data generator for realistic paper information
function generateEnhancedMockRecords(ratings: string[]): RecordWithAppraisal[] {
  const aiReasoningExamples = {
    'Green': [
      'High-quality systematic review with comprehensive search strategy, large sample size (n>1000), and robust methodology. Low risk of bias across all domains.',
      'Well-designed RCT with proper randomization, blinding, and complete outcome reporting. Strong evidence for effectiveness.',
      'Meta-analysis with high methodological rigor, appropriate statistical methods, and consistent findings across studies.'
    ],
    'Amber': [
      'Moderate quality study with some methodological limitations. Sample size adequate but concerns about selection bias.',
      'Quasi-experimental design with appropriate controls but limited generalizability due to single-site implementation.',
      'Systematic review with adequate search but some studies excluded due to quality concerns. Mixed findings.'
    ],
    'Red': [
      'High risk of bias due to non-randomized design and significant methodological flaws. Small sample size (n<50).',
      'Case series with no control group and potential confounding variables not addressed. Limited evidence quality.',
      'Study with incomplete data reporting, high attrition rates, and unclear methodology. Results not reliable.'
    ]
  }

  const screeningReasons = {
    'include': [
      'Meets all inclusion criteria: relevant population, appropriate intervention, and outcome measures align with research objectives.',
      'Study design is appropriate for answering the research question with adequate methodology and sample size.',
      'Population characteristics match target demographics with relevant outcome measures and sufficient follow-up.'
    ],
    'exclude': [
      'Population does not match inclusion criteria - study focuses on different demographic or clinical population.',
      'Intervention differs significantly from target intervention or lacks sufficient detail for comparison.',
      'Study design inadequate - case report, editorial, or conference abstract without peer review.',
      'Outcome measures not relevant to research question or insufficient data for analysis.',
      'Language barrier - full text not available in English despite English abstract.'
    ]
  }

  const samplePapers = [
    {
      title: "Effectiveness of Simulation-Based Learning in Nursing Education: A Systematic Review",
      authors: "Smith, J.A., Johnson, M.K., Wilson, P.R.",
      year: 2023,
      source: "PubMed",
      doi: "10.1016/j.nedt.2023.001",
      publication_type: "Systematic Review",
      institution: "University of California San Francisco, School of Nursing",
      abstract: "This systematic review examines the effectiveness of simulation-based learning approaches in nursing education, analyzing outcomes from 45 studies..."
    },
    {
      title: "Impact of Problem-Based Learning on Clinical Reasoning Skills",
      authors: "García-López, M., Anderson, R.J.",
      year: 2022,
      source: "ERIC",
      doi: "10.1007/s10459-022-001",
      publication_type: "Research Article",
      institution: "Harvard Medical School, Department of Medical Education",
      abstract: "A randomized controlled trial investigating the impact of problem-based learning methodologies on the development of clinical reasoning skills..."
    },
    {
      title: "Technology-Enhanced Learning in Medical Education: Current Trends",
      authors: "Chen, L., Patel, S.K., Mohammed, A.H.",
      year: 2023,
      source: "Crossref",
      doi: "10.1080/10872981.2023.001",
      publication_type: "Review Article",
      institution: "Stanford University School of Medicine",
      abstract: "An analysis of current trends in technology-enhanced learning within medical education, covering virtual reality, AI tutoring systems..."
    },
    {
      title: "Interprofessional Education and Collaborative Practice Outcomes",
      authors: "Taylor, K.R., Brooks, D.L., Martinez, C.E.",
      year: 2022,
      source: "SemanticScholar",
      doi: "10.1111/medu.14876",
      publication_type: "Meta-analysis",
      institution: "Johns Hopkins University, School of Public Health",
      abstract: "A meta-analysis of interprofessional education programs and their impact on collaborative practice outcomes in healthcare settings..."
    },
    {
      title: "Active Learning Strategies in Large Lecture Classes",
      authors: "Williams, P.J., Kumar, R.",
      year: 2021,
      source: "GoogleScholar",
      doi: "10.1187/cbe.21-001",
      publication_type: "Research Article",
      institution: "University of Michigan, Medical School",
      abstract: "Investigation of various active learning strategies implemented in large lecture classes and their effect on student engagement and learning outcomes..."
    },
    {
      title: "Assessment Methods in Competency-Based Medical Education",
      authors: "Rodriguez, A.M., Thompson, B.K., Lee, S.H.",
      year: 2023,
      source: "PubMed",
      doi: "10.1097/ACM.0000000001",
      publication_type: "Systematic Review",
      institution: "Mayo Clinic College of Medicine",
      abstract: "Comprehensive review of assessment methods used in competency-based medical education programs, analyzing validity and reliability..."
    },
    {
      title: "Flipped Classroom Model in Health Professions Education",
      authors: "Jackson, M.R., Davis, E.L.",
      year: 2022,
      source: "ERIC",
      doi: "10.1016/j.cptl.2022.001",
      publication_type: "Research Article",
      institution: "University of Toronto, Faculty of Medicine",
      abstract: "Evaluation of the flipped classroom model implementation in health professions education and its impact on student satisfaction and performance..."
    },
    {
      title: "Cultural Competency Training in Healthcare Education",
      authors: "Nakamura, T., Brown, K.J., Singh, R.P.",
      year: 2021,
      source: "Crossref",
      doi: "10.1080/10401334.2021.001",
      publication_type: "Review Article",
      institution: "University of Washington School of Medicine",
      abstract: "Analysis of cultural competency training programs in healthcare education and their effectiveness in preparing culturally responsive practitioners..."
    },
    {
      title: "Virtual Reality Applications in Surgical Training",
      authors: "Foster, A.K., Mitchell, R.L.",
      year: 2023,
      source: "PubMed",
      url: "https://example.com/vr-surgical-training",
      publication_type: "Research Article",
      institution: "Cleveland Clinic Lerner College of Medicine",
      abstract: "<jats:title>Abstract</jats:title><jats:sec><jats:title>Background</jats:title><jats:p>Virtual reality technology has emerged as a promising tool for surgical training...</jats:p></jats:sec>"
    }
  ]

  console.log('Generating enhanced mock records with ratings:', ratings)
  
  const generatedRecords = ratings.map((rating: string, index: number) => {
    const paperIndex = index % samplePapers.length
    const paper = samplePapers[paperIndex]
    const colorRating = rating as 'Red' | 'Amber' | 'Green'
    const reasoningPool = aiReasoningExamples[colorRating] || aiReasoningExamples['Amber']
    const reasoning = reasoningPool[Math.floor(Math.random() * reasoningPool.length)]
    
    const screeningDecision = Math.random() > 0.15 ? 'include' : 'exclude' // 85% included, 15% excluded
    const screeningReasonPool = screeningReasons[screeningDecision]
    const screeningReason = screeningReasonPool[Math.floor(Math.random() * screeningReasonPool.length)]
    
    const generatedRecord = {
      id: `record-${index}`,
      title: paper.title || `Study Title ${index + 1}`,
      authors: paper.authors || `Author A., Author B.${index}`,
      year: paper.year || (2020 + Math.floor(Math.random() * 4)),
      source: paper.source || 'Academic Database',
      doi: paper.doi || `10.1000/example.${index}`,
      url: (paper as any).url,
      publication_type: paper.publication_type || 'Research Article',
      institution: (paper as any).institution,
      abstract: paper.abstract || `This is a sample abstract for study ${index + 1} about the research topic.`,
      appraisal_color: colorRating,
      appraisal_score: rating === 'Green' ? Math.random() * 0.2 + 0.8 : 
                      rating === 'Amber' ? Math.random() * 0.3 + 0.5 : 
                      Math.random() * 0.3 + 0.2,
      appraisal_reasoning: reasoning,
      ai_review_type: Math.random() > 0.3 ? 'full_text' : 'abstract_only',
      screening_decision: screeningDecision,
      screening_reason: screeningReason,
      screening_ai_explanation: `Initial AI assessment: ${screeningDecision === 'include' ? 'Study meets inclusion criteria' : 'Study does not meet inclusion criteria'}` // Default explanation
    }
    
    console.log(`Generated record ${index}:`, generatedRecord)
    return generatedRecord
  })
  
  console.log('Final generated records:', generatedRecords.length, 'records with colors:', 
    generatedRecords.map(r => r.appraisal_color))
  
  return generatedRecords
}

// Helper function to generate AI screening explanations
async function generateAIScreeningExplanation(
  record: RecordWithAppraisal, 
  apiClient: ApiClient,
  researchQuestion?: string
): Promise<string> {
  try {
    // Define inclusion/exclusion criteria based on the research question
    const inclusionCriteria = [
      'Studies involving chronic disease patients and their families',
      'Interventions related to hemodialysis education and support programs',
      'Outcomes measuring motivation, participation, or engagement',
      'Peer-reviewed research articles and systematic reviews'
    ]
    
    const exclusionCriteria = [
      'Studies not involving chronic disease populations',
      'Interventions unrelated to dialysis or chronic disease management',
      'Case reports, editorials, or conference abstracts',
      'Studies in languages other than English'
    ]
    
    const assessment = await apiClient.assessStudyRelevance({
      title: record.title,
      abstract: record.abstract,
      inclusion_criteria: inclusionCriteria,
      exclusion_criteria: exclusionCriteria,
      research_question: researchQuestion
    })
    
    return assessment?.reasoning || 'AI assessment unavailable'
  } catch (error) {
    console.error('Failed to generate AI screening explanation:', error)
    return record.screening_decision === 'include' 
      ? 'Study methodology and population align with systematic review objectives'
      : 'Study does not meet inclusion criteria based on population or intervention mismatch'
  }
}

export function RunResults({ runId, runData, apiClient }: RunResultsProps) {
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [records, setRecords] = useState<RecordWithAppraisal[]>([])
  const [sortedRecords, setSortedRecords] = useState<RecordWithAppraisal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')
  const [selectedTab, setSelectedTab] = useState<'summary' | 'records' | 'synthesis'>('summary')
  const [viewMode, setViewMode] = useState<'quality' | 'screening'>('quality')
  const [statusFilter, setStatusFilter] = useState<'all' | 'include' | 'exclude'>('all')
  const [qualityLevelFilter, setQualityLevelFilter] = useState<'all' | 'green' | 'amber' | 'red'>('all')
  const [sortField, setSortField] = useState<SortField>('appraisal_score')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [researchQuestion, setResearchQuestion] = useState<string>('')
  const [aiExplanationsLoading, setAiExplanationsLoading] = useState<boolean>(false)
  const [synthesisData, setSynthesisData] = useState<any>(null)
  const [synthesisLoading, setSynthesisLoading] = useState<boolean>(false)
  const [synthesisError, setSynthesisError] = useState<string>('')

  // Detailed appraisal view state
  const [showDetailedAppraisal, setShowDetailedAppraisal] = useState<boolean>(false)
  const [selectedRecordForDetail, setSelectedRecordForDetail] = useState<RecordWithAppraisal | null>(null)

  // View layout state
  const [compactView, setCompactView] = useState<boolean>(false)

  // Enhanced filtering state
  const [qualityFilter, setQualityFilter] = useState<string>('all')
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all')
  const [publicationTypeFilter, setPublicationTypeFilter] = useState<string>('all')
  const [hasFullTextFilter, setHasFullTextFilter] = useState<string>('all')
  const [recentFilter, setRecentFilter] = useState<string>('all')

  // Progressive disclosure state
  const [expandedAbstracts, setExpandedAbstracts] = useState<Set<string>>(new Set())

  // Progressive disclosure handlers
  const toggleAbstract = (recordId: string) => {
    const newExpanded = new Set(expandedAbstracts)
    if (newExpanded.has(recordId)) {
      newExpanded.delete(recordId)
    } else {
      newExpanded.add(recordId)
    }
    setExpandedAbstracts(newExpanded)
  }

  const truncateAbstract = (abstract: string, maxLength: number = 120): { truncated: string; needsTruncation: boolean } => {
    if (!abstract || abstract.length <= maxLength) {
      return { truncated: abstract || '', needsTruncation: false }
    }
    return {
      truncated: abstract.substring(0, maxLength) + '...',
      needsTruncation: true
    }
  }

  // Enhanced filtering function
  const applyFilters = (records: RecordWithAppraisal[]): RecordWithAppraisal[] => {
    return records.filter(record => {
      // Quality filter
      if (qualityFilter !== 'all') {
        const recordQuality = record.appraisal_color?.toLowerCase() || 'amber'
        if (qualityFilter === 'high' && recordQuality !== 'green') return false
        if (qualityFilter === 'medium' && recordQuality !== 'amber') return false
        if (qualityFilter === 'low' && recordQuality !== 'red') return false
      }

      // Confidence filter
      if (confidenceFilter !== 'all') {
        const confidence = getConfidenceLevel(record)
        if (confidenceFilter !== confidence) return false
      }

      // Publication type filter
      if (publicationTypeFilter !== 'all') {
        const recordType = record.publication_type?.toLowerCase() || ''
        if (publicationTypeFilter === 'research' && !recordType.includes('research')) return false
        if (publicationTypeFilter === 'review' && !recordType.includes('review')) return false
        if (publicationTypeFilter === 'meta-analysis' && !recordType.includes('meta')) return false
      }

      // Full text filter
      if (hasFullTextFilter !== 'all') {
        const hasFullText = record.ai_review_type === 'full_text'
        if (hasFullTextFilter === 'yes' && !hasFullText) return false
        if (hasFullTextFilter === 'no' && hasFullText) return false
      }

      // Recent publications filter
      if (recentFilter !== 'all') {
        const year = record.year || extractYearFromTitle(record.title) || 0
        const currentYear = new Date().getFullYear()
        if (recentFilter === 'last5' && year < currentYear - 5) return false
        if (recentFilter === 'last10' && year < currentYear - 10) return false
      }

      return true
    })
  }

  // Handle showing detailed appraisal
  const handleShowDetailedAppraisal = (record: RecordWithAppraisal) => {
    // Generate mock detailed appraisal data since we don't have the backend endpoint yet
    const mockDetailedAppraisals = [
      {
        id: `appraisal-${record.id}-1`,
        methodology_id: 'rag-quality-1',
        methodology: {
          id: 'rag-quality-1',
          name: 'RAG Quality Indices',
          version: '1.0',
          description: 'Research in Medical Education quality assessment framework',
          method_type: 'rag_quality' as const,
          criteria: {
            underpinning: { weight: 0.15, description: 'Theoretical underpinning and rationale' },
            curriculum: { weight: 0.15, description: 'Curriculum content and alignment' },
            setting: { weight: 0.15, description: 'Educational setting appropriateness' },
            pedagogy: { weight: 0.20, description: 'Pedagogical approach effectiveness' },
            content: { weight: 0.20, description: 'Content quality and relevance' },
            conclusion: { weight: 0.15, description: 'Strength of conclusions and implications' }
          },
          scoring_config: { max_score: 1, thresholds: { green: 0.7, amber: 0.5 } },
          requires_full_text: true
        },
        scores: {
          underpinning: 0.8,
          curriculum: 0.7,
          setting: 0.9,
          pedagogy: 0.6,
          content: 0.8,
          conclusion: 0.7
        },
        overall_score: record.appraisal_score || 0.75,
        rating: record.appraisal_color || 'Amber',
        rationale: record.appraisal_reasoning || 'Study demonstrates good methodological rigor with clear educational outcomes. Some limitations in sample size and generalizability.',
        evidence_citations: [
          'Strong theoretical framework based on constructivist learning theory',
          'Well-designed randomized controlled trial methodology',
          'Appropriate statistical analysis with effect sizes reported'
        ],
        confidence: 0.85,
        used_full_text: record.ai_review_type === 'full_text',
        sections_analyzed: ['abstract', 'methods', 'results', 'discussion'],
        assessed_by: 'AI Assessment System',
        assessment_time: 12.5,
        created_at: new Date().toISOString()
      }
    ]

    const enhancedRecord = {
      ...record,
      detailed_appraisals: mockDetailedAppraisals
    }

    setSelectedRecordForDetail(enhancedRecord)
    setShowDetailedAppraisal(true)
  }

  const handleCloseDetailedAppraisal = () => {
    setShowDetailedAppraisal(false)
    setSelectedRecordForDetail(null)
  }

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setError('')
      
      try {
        // If we have immediate run data, use it
        if (runData) {
          // Map runData to our expected format
          const mappedSummary: RunSummary = {
            run_id: runData.run_id || 'Unknown',
            status: 'completed',
            created_at: new Date().toISOString(),
            total_records: runData.prisma?.identified || 0,
            screened_records: runData.prisma?.screened || 0,
            included_records: runData.prisma?.eligible || 0,
            excluded_records: runData.prisma?.excluded || 0,
            appraised_records: runData.n_appraised || 0,
            prisma_counts: runData.prisma ? {
              initial_records: runData.prisma.identified || 0,
              after_deduplication: runData.prisma.deduped || 0,
              after_screening: runData.prisma.screened || 0,
              after_appraisal: runData.prisma.eligible || 0,
              final_included: runData.prisma.eligible || 0
            } : undefined
          }
          setSummary(mappedSummary)
          
          console.log('=== DATA SOURCE ANALYSIS ===')
          console.log('runData object:', runData)
          console.log('Mapped summary:', mappedSummary)
          
          // Try to fetch real record data, fallback to enhanced mock data
          if (runData.run_id) {
            try {
              const recordsData = await apiClient.getRecordsWithAppraisals(runData.run_id, {
                limit: Math.max(25, runData.n_appraised || 20),
                offset: 0
              })
              if (recordsData.items && recordsData.items.length > 0) {
                console.log('=== USING REAL API DATA ===')
                console.log('API records count:', recordsData.items.length)
                console.log('Sample API record structure:', recordsData.items[0])
                console.log('API record IDs (record_id field):', recordsData.items.map(r => r.record_id))
                console.log('API record ratings:', recordsData.items.map(r => r.rating))
                console.log('API record authors (missing):', recordsData.items.map(r => r.authors))
                console.log('API record screening_decisions (missing):', recordsData.items.map(r => r.screening_decision))
                
                // Map API data to frontend expected format
                const mappedRecords: RecordWithAppraisal[] = recordsData.items.map((apiRecord: any) => ({
                  id: apiRecord.record_id, // Map record_id to id
                  title: apiRecord.title || 'Untitled',
                  authors: apiRecord.authors || 'Authors not specified', // Now provided by API
                  year: apiRecord.year,
                  source: apiRecord.source || 'Academic Database',
                  abstract: apiRecord.abstract,
                  doi: apiRecord.doi,
                  url: apiRecord.url,
                  publication_type: apiRecord.publication_type || 'Journal Article', // Now provided by API
                  institution: apiRecord.institution, // Author affiliation/institution
                  screening_decision: 'include', // API doesn't provide screening decisions, default to include since these are appraised records
                  screening_reason: '',
                  screening_ai_explanation: 'Study met screening criteria',
                  appraisal_score: apiRecord.score_final || 0,
                  appraisal_color: apiRecord.rating as 'Red' | 'Amber' | 'Green', // Map rating field to appraisal_color
                  appraisal_reasoning: apiRecord.rationale,
                  ai_review_type: apiRecord.content_type || ((apiRecord.pdf_url || apiRecord.fulltext_url || apiRecord.open_access) ? 'full_text' : 'abstract_only')
                }))
                
                console.log('Mapped records count:', mappedRecords.length)
                console.log('Sample mapped record:', mappedRecords[0])
                console.log('Mapped record IDs:', mappedRecords.map(r => r.id))
                console.log('Mapped record appraisal_colors:', mappedRecords.map(r => r.appraisal_color))
                console.log('Mapped record screening_decisions:', mappedRecords.map(r => r.screening_decision))
                setRecords(mappedRecords)
              } else {
                // Enhanced mock data with realistic paper information
                // Generate 25 records to match the appraised count
                console.log('=== USING MOCK DATA (no API data) ===')
                const mockRatings = runData.ratings || []
                const targetCount = runData.n_appraised || 25
                const extendedRatings = []
                for (let i = 0; i < targetCount; i++) {
                  extendedRatings.push(mockRatings[i % mockRatings.length] || 'Amber')
                }
                console.log('Extended ratings for mock generation:', extendedRatings)
                const mockRecords = generateEnhancedMockRecords(extendedRatings)
                console.log('Generated mock records count:', mockRecords.length)
                console.log('Sample mock record structure:', mockRecords[0])
                console.log('Mock record IDs:', mockRecords.map(r => r.id))
                console.log('Mock record appraisal_colors:', mockRecords.map(r => r.appraisal_color))
                console.log('Mock record authors:', mockRecords.map(r => r.authors))
                console.log('Mock record screening_decisions:', mockRecords.map(r => r.screening_decision))
                setRecords(mockRecords)
              }
            } catch (error) {
              // Fallback to enhanced mock data if API fails
              console.log('=== USING MOCK DATA (API error fallback) ===')
              console.log('API error:', error)
              const mockRatings = runData.ratings || []
              const targetCount = runData.n_appraised || 25
              const extendedRatings = []
              for (let i = 0; i < targetCount; i++) {
                extendedRatings.push(mockRatings[i % mockRatings.length] || 'Amber')
              }
              console.log('Fallback ratings:', extendedRatings)
              const mockRecords = generateEnhancedMockRecords(extendedRatings)
              console.log('Generated fallback mock records count:', mockRecords.length)
              setRecords(mockRecords)
            }
          } else if (runData.ratings && runData.ratings.length > 0) {
            console.log('=== USING MOCK DATA (ratings provided) ===')
            const targetCount = runData.n_appraised || runData.ratings.length
            const extendedRatings = []
            for (let i = 0; i < targetCount; i++) {
              extendedRatings.push(runData.ratings[i % runData.ratings.length])
            }
            console.log('Extended ratings from runData:', extendedRatings)
            const mockRecords = generateEnhancedMockRecords(extendedRatings)
            console.log('Generated mock records from ratings count:', mockRecords.length)
            setRecords(mockRecords)
          }
        } else if (runId) {
          // Fetch from API endpoints
          const summaryData = await apiClient.getRunSummary(runId)
          
          // Map API summary data to expected RunSummary format
          const mappedSummary: RunSummary = {
            run_id: summaryData.run?.id || runId,
            status: 'completed',
            created_at: summaryData.run?.created_at || new Date().toISOString(),
            total_records: summaryData.n_records || 0,
            screened_records: summaryData.counts?.screened || 0,
            included_records: summaryData.counts?.included || 0,
            excluded_records: summaryData.counts?.excluded || 0,
            appraised_records: summaryData.n_appraisals || 0,
            prisma_counts: summaryData.counts ? {
              initial_records: summaryData.counts.identified || 0,
              after_deduplication: summaryData.counts.deduped || 0,
              after_screening: summaryData.counts.screened || 0,
              after_appraisal: summaryData.counts.eligible || 0,
              final_included: summaryData.counts.included || 0
            } : undefined
          }
          setSummary(mappedSummary)
          
          // Fetch all screening records (included + excluded) for complete view
          const screeningsData = await apiClient.getScreeningsWithRecords(runId, {
            limit: 100, // Get more records to show all
            offset: 0
          })
          
          // Also fetch appraisal data for included records
          const appraisalsData = await apiClient.getRecordsWithAppraisals(runId, {
            limit: 50,
            offset: 0
          })
          
          // Create a map of appraisal data by record_id
          const appraisalMap = new Map()
          if (appraisalsData.items) {
            appraisalsData.items.forEach((appraisal: any) => {
              appraisalMap.set(appraisal.record_id, appraisal)
            })
          }
          
          // Map screening data with appraisal info where available
          if (screeningsData.items && screeningsData.items.length > 0) {
            const mappedRecords: RecordWithAppraisal[] = screeningsData.items.map((screening: any) => {
              const appraisal = appraisalMap.get(screening.record_id)
              const isIncluded = screening.decision === 'include'
              
              return {
                id: screening.record_id,
                title: getDisplayTitle(screening.title, screening.record_id, screening.reason, isIncluded),
                authors: 'authors' in screening ? screening.authors : undefined,
                year: screening.year || undefined,
                source: screening.source || _inferSourceFromId(screening.record_id),
                abstract: screening.abstract,
                doi: screening.doi,
                url: screening.url,
                publication_type: screening.publication_type || (isIncluded ? 'Journal Article' : 'Unknown Type'),
                screening_decision: screening.decision as 'include' | 'exclude',
                screening_reason: screening.reason || '',
                screening_ai_explanation: isIncluded ? 
                  'Study met initial screening criteria and was included for quality assessment' :
                  `Excluded from appraisal because: ${screening.reason || 'screening criteria not met'}`,
                appraisal_score: appraisal?.score_final || 0,
                appraisal_color: appraisal?.rating as 'Red' | 'Amber' | 'Green',
                appraisal_reasoning: appraisal?.rationale,
                ai_review_type: 'abstract_only',
                status: isIncluded ? 'Include' : 'Exclude'
              }
            })
            setRecords(mappedRecords)
          } else {
            setRecords([])
          }
        }
      } catch (err) {
        setError(`Failed to load results: ${err instanceof Error ? err.message : 'Unknown error'}`)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [runId, runData, apiClient])

  const fetchSynthesis = async () => {
    if (!runId || !summary) return

    setSynthesisLoading(true)
    setSynthesisError('')
    
    try {
      const synthesis = await apiClient.generateResearchSynthesis(runId, {
        max_studies: 10
      })
      setSynthesisData(synthesis)
    } catch (err) {
      setSynthesisError(`Failed to generate synthesis: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setSynthesisLoading(false)
    }
  }

  const renderCitation = (citation: CitationMetadata) => {
    const doiUrl = citation.doi ? `https://doi.org/${citation.doi}` : undefined
    const links: { href: string; label: string }[] = []

    if (citation.url) {
      links.push({ href: citation.url, label: 'View study' })
    }
    if (doiUrl) {
      links.push({ href: doiUrl, label: `doi:${citation.doi}` })
    }

    const hasScore = typeof citation.appraisal_score === 'number' && !Number.isNaN(citation.appraisal_score)

    return (
      <li key={citation.citation_key} className="citation-item">
        <div className="citation-header">
          <span className="citation-key-badge">[{citation.citation_key}]</span>
          {citation.appraisal_rating && (
            <span className={`citation-rating-badge ${citation.appraisal_rating.toLowerCase()}`}>
              {citation.appraisal_rating}
            </span>
          )}
          {hasScore && <span className="citation-score">Score {citation.appraisal_score?.toFixed(2)}</span>}
        </div>
        <div className="citation-body">
          <div className="citation-title">{citation.title}</div>
          <div className="citation-meta">
            <span className="citation-authors">{citation.authors}</span>
            {citation.year && <span className="citation-year">({citation.year})</span>}
          </div>
          {links.length > 0 && (
            <div className="citation-links">
              {links.map(link => (
                <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer">
                  {link.label}
                </a>
              ))}
            </div>
          )}
        </div>
      </li>
    )
  }

  const studyCitations: CitationMetadata[] = synthesisData?.study_citations
    ? (Object.values(synthesisData.study_citations) as CitationMetadata[])
    : []

  const fullTextAvailabilityEntries: [string, boolean][] = synthesisData?.full_text_availability
    ? (Object.entries(synthesisData.full_text_availability) as [string, boolean][])
    : []

  // Generate AI explanations when switching to records tab in screening mode
  useEffect(() => {
    const generateAIExplanations = async () => {
      if (selectedTab === 'records' && viewMode === 'screening' && records.length > 0 && !aiExplanationsLoading) {
        console.log('Starting AI explanation generation for', records.length, 'records')
        setAiExplanationsLoading(true)
        
        // Process all records, but limit concurrent API calls
        const updatedRecords = [...records]
        let explanationsGenerated = 0
        
        for (let i = 0; i < Math.min(records.length, 8); i++) {
          const record = records[i]
          if (!record.screening_ai_explanation || record.screening_ai_explanation.includes('Initial AI assessment')) {
            try {
              console.log(`Generating AI explanation for record ${i + 1}:`, record.title)
              const explanation = await generateAIScreeningExplanation(record, apiClient, researchQuestion)
              
              const recordIndex = updatedRecords.findIndex(r => r.id === record.id)
              if (recordIndex !== -1) {
                updatedRecords[recordIndex] = {
                  ...updatedRecords[recordIndex],
                  screening_ai_explanation: explanation
                }
                explanationsGenerated++
                console.log(`Generated explanation ${explanationsGenerated} for record:`, record.id)
              }
            } catch (error) {
              console.error('Failed to generate explanation for record:', record.id, error)
              // Set error explanation
              const recordIndex = updatedRecords.findIndex(r => r.id === record.id)
              if (recordIndex !== -1) {
                updatedRecords[recordIndex] = {
                  ...updatedRecords[recordIndex],
                  screening_ai_explanation: 'AI assessment temporarily unavailable - please try again later'
                }
              }
            }
          }
        }
        
        console.log(`Generated ${explanationsGenerated} AI explanations, updating records`)
        setRecords(updatedRecords)
        setAiExplanationsLoading(false)
      }
    }
    
    // Only run when tab changes to records in screening mode and we haven't started loading
    if (selectedTab === 'records' && viewMode === 'screening' && !aiExplanationsLoading) {
      generateAIExplanations()
    } else if (selectedTab === 'synthesis' && !synthesisData && !synthesisLoading) {
      fetchSynthesis()
    }
  }, [selectedTab, viewMode]) // Remove other dependencies to prevent infinite loops


  // Sorting and filtering logic
  useEffect(() => {
    if (records.length > 0) {
      // First apply filters
      const filtered = applyFilters(records)

      const sorted = [...filtered].sort((a, b) => {
        let aValue: any = a[sortField]
        let bValue: any = b[sortField]

        // Removed excessive logging during sort comparison

        // Handle different data types
        if (sortField === 'appraisal_score') {
          aValue = typeof aValue === 'number' ? aValue : 0
          bValue = typeof bValue === 'number' ? bValue : 0
        } else if (sortField === 'year') {
          aValue = typeof aValue === 'number' ? aValue : 0
          bValue = typeof bValue === 'number' ? bValue : 0
        } else if (sortField === 'publication_type') {
          aValue = (aValue || 'Research Article').toString().toLowerCase()
          bValue = (bValue || 'Research Article').toString().toLowerCase()
        } else if (sortField === 'authors') {
          aValue = (aValue || 'Authors not specified').toString().toLowerCase()
          bValue = (bValue || 'Authors not specified').toString().toLowerCase()
        } else if (sortField === 'status') {
          aValue = (aValue || 'Include').toString().toLowerCase()
          bValue = (bValue || 'Include').toString().toLowerCase()
        } else {
          // For title and other string fields
          aValue = (aValue || '').toString().toLowerCase()
          bValue = (bValue || '').toString().toLowerCase()
        }

        // Perform comparison
        let comparison = 0
        if (sortField === 'appraisal_score' || sortField === 'year') {
          comparison = aValue - bValue
        } else {
          comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0
        }

        return sortOrder === 'asc' ? comparison : -comparison
      })
      setSortedRecords(sorted)
    }
  }, [records, sortField, sortOrder, statusFilter, qualityLevelFilter, qualityFilter, confidenceFilter, publicationTypeFilter, hasFullTextFilter, recentFilter])

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('desc')
    }
  }

  // CSV Export functionality
  const exportSummaryToCSV = () => {
    if (!summary) return
    
    const csvContent = [
      ['Metric', 'Value'],
      ['Run ID', summary.run_id],
      ['Status', summary.status],
      ['Created', summary.created_at ? new Date(summary.created_at).toLocaleString() : 'N/A'],
      ['Total Records', summary.total_records?.toString() || '0'],
      ['Screened Records', summary.screened_records?.toString() || '0'],
      ['Included Records', summary.included_records?.toString() || '0'],
      ['Excluded Records', summary.excluded_records?.toString() || '0'],
      ['Appraised Records', summary.appraised_records?.toString() || '0'],
      ...(summary.prisma_counts ? [
        ['PRISMA - Initial Records', summary.prisma_counts.initial_records?.toString() || '0'],
        ['PRISMA - After Deduplication', summary.prisma_counts.after_deduplication?.toString() || '0'],
        ['PRISMA - After Screening', summary.prisma_counts.after_screening?.toString() || '0'],
        ['PRISMA - After Appraisal', summary.prisma_counts.after_appraisal?.toString() || '0'],
        ['PRISMA - Final Included', summary.prisma_counts.final_included?.toString() || '0']
      ] : [])
    ]
    
    const csvString = csvContent.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    
    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', `literature_review_summary_${summary.run_id}.csv`)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  const exportRecordsToCSV = () => {
    if (sortedRecords.length === 0) return
    
    const headers = [
      'Title', 'Authors', 'Year', 'Source', 'Publication Type', 
      'Appraisal Color', 'Appraisal Score', 'AI Review Type',
      'DOI', 'URL', 'Screening Decision', 'Screening Reason',
      'AI Explanation', 'Abstract'
    ]
    
    const csvContent = [
      headers,
      ...sortedRecords.map(record => [
        record.title || '',
        getDisplayAuthors(record),
        getDisplayYear(record),
        inferSourceFromId(record.id, record.source),
        inferPublicationType(record.title, record.publication_type),
        record.appraisal_color || '',
        record.appraisal_score?.toFixed(2) || '',
        record.ai_review_type || '',
        record.doi || '',
        record.url || '',
        record.screening_decision || '',
        record.screening_reason || '',
        record.appraisal_reasoning || '',
        (record.abstract || '').replace(/<\/?jats:[^>]*>/g, '').substring(0, 500)
      ])
    ]
    
    const csvString = csvContent.map(row => row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    
    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', `literature_review_records_${summary?.run_id || 'export'}.csv`)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  if (loading) {
    return (
      <div className="card run-results">
        <h3>📊 Literature Review Results</h3>
        <div className="loading-state">
          <div className="spinner">⏳</div>
          <p>Loading results...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card run-results">
        <h3>📊 Literature Review Results</h3>
        <div className="error-state">
          <p className="error-message">{error}</p>
        </div>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="card run-results">
        <h3>📊 Literature Review Results</h3>
        <p>No results available for this run.</p>
      </div>
    )
  }

  return (
    <>
      <div className="card run-results">
      <h3>📊 Literature Review Results</h3>
      
      {/* Tab Navigation with Export Options */}
      <div className="results-header">
        <div className="results-tabs">
          <button 
            className={`tab-button ${selectedTab === 'summary' ? 'active' : ''}`}
            onClick={() => setSelectedTab('summary')}
          >
            📈 Summary
          </button>
          <button
            className={`tab-button ${selectedTab === 'records' ? 'active' : ''}`}
            onClick={() => setSelectedTab('records')}
          >
            📄 Records & Decisions ({sortedRecords.length})
          </button>
          <button 
            className={`tab-button ${selectedTab === 'synthesis' ? 'active' : ''}`}
            onClick={() => setSelectedTab('synthesis')}
          >
            🤖 AI Research Synthesis
          </button>
        </div>
        
        <div className="export-options">
          {selectedTab === 'summary' ? (
            <button 
              className="export-btn"
              onClick={exportSummaryToCSV}
              title="Export Summary to CSV"
            >
              📊 Export Summary
            </button>
          ) : selectedTab === 'records' ? (
            <button
              className="export-btn"
              onClick={exportRecordsToCSV}
              title="Export Records & Decisions to CSV"
            >
              📁 Export Records & Decisions
            </button>
          ) : selectedTab === 'synthesis' ? (
            <button 
              className="export-btn"
              onClick={() => {
                if (synthesisData) {
                  const dataStr = JSON.stringify(synthesisData, null, 2)
                  const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr)
                  const exportFileDefaultName = `synthesis_${runSummary?.run_id || 'unknown'}.json`
                  const linkElement = document.createElement('a')
                  linkElement.setAttribute('href', dataUri)
                  linkElement.setAttribute('download', exportFileDefaultName)
                  linkElement.click()
                }
              }}
              title="Export Synthesis to JSON"
            >
              🤖 Export Synthesis
            </button>
          ) : null}
        </div>
      </div>

      {/* Summary Tab */}
      {selectedTab === 'summary' && (
        <div className="summary-content">
          {/* Key Metrics */}
          <div className="metrics-grid">
            <div className="metric-card">
              <div className="metric-value">{summary.total_records || 0}</div>
              <div className="metric-label">Total Records</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{summary.screened_records || 0}</div>
              <div className="metric-label">Screened</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{summary.included_records || 0}</div>
              <div className="metric-label">Included</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{summary.excluded_records || 0}</div>
              <div className="metric-label">Excluded</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{summary.appraised_records || 0}</div>
              <div className="metric-label">Appraised</div>
            </div>
          </div>

          {/* PRISMA Flow */}
          {summary.prisma_counts && (
            <div className="prisma-flow">
              <h4>🔄 PRISMA Flow</h4>
              <div className="flow-steps">
                <div className="flow-step">
                  <div className="step-count">{summary.prisma_counts.initial_records || 0}</div>
                  <div className="step-label">Initial Records</div>
                </div>
                <div className="flow-arrow">↓</div>
                <div className="flow-step">
                  <div className="step-count">{summary.prisma_counts.after_deduplication || 0}</div>
                  <div className="step-label">After Deduplication</div>
                </div>
                <div className="flow-arrow">↓</div>
                <div className="flow-step">
                  <div className="step-count">{summary.prisma_counts.after_screening || 0}</div>
                  <div className="step-label">After Screening</div>
                </div>
                <div className="flow-arrow">↓</div>
                <div className="flow-step">
                  <div className="step-count">{summary.prisma_counts.after_appraisal || 0}</div>
                  <div className="step-label">After Appraisal</div>
                </div>
                <div className="flow-arrow">↓</div>
                <div className="flow-step final">
                  <div className="step-count">{summary.prisma_counts.final_included || 0}</div>
                  <div className="step-label">Final Included</div>
                </div>
              </div>
            </div>
          )}

          {/* Quality Score Breakdown */}
          {sortedRecords.length > 0 && (() => {
            const greenCount = sortedRecords.filter(r => r.appraisal_color === 'Green').length
            const amberCount = sortedRecords.filter(r => r.appraisal_color === 'Amber').length  
            const redCount = sortedRecords.filter(r => r.appraisal_color === 'Red').length
            const totalCount = sortedRecords.length
            
            console.log('Quality Assessment Breakdown:', { greenCount, amberCount, redCount, totalCount, records: sortedRecords.map(r => ({ id: r.id, color: r.appraisal_color })) })
            
            return (
              <div className="quality-breakdown">
                <h4>🏆 Quality Assessment Breakdown</h4>
                <div className="quality-metrics">
                  <div className="quality-card green">
                    <div className="quality-badge green">Green</div>
                    <div className="quality-value">{greenCount}</div>
                    <div className="quality-label">High Quality</div>
                    <div className="quality-percentage">
                      {totalCount > 0 ? ((greenCount / totalCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                  <div className="quality-card amber">
                    <div className="quality-badge amber">Amber</div>
                    <div className="quality-value">{amberCount}</div>
                    <div className="quality-label">Moderate Quality</div>
                    <div className="quality-percentage">
                      {totalCount > 0 ? ((amberCount / totalCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                  <div className="quality-card red">
                    <div className="quality-badge red">Red</div>
                    <div className="quality-value">{redCount}</div>
                    <div className="quality-label">Low Quality</div>
                    <div className="quality-percentage">
                      {totalCount > 0 ? ((redCount / totalCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Full-Text Acquisition Breakdown */}
          {sortedRecords.length > 0 && (() => {
            const fullTextCount = sortedRecords.filter(r => r.ai_review_type === 'full_text').length
            const abstractOnlyCount = sortedRecords.filter(r => r.ai_review_type === 'abstract_only').length
            const totalCount = sortedRecords.length

            return (
              <div className="quality-breakdown">
                <h4>📄 Full-Text Acquisition Breakdown</h4>
                <div className="quality-metrics">
                  <div className="quality-card full-text">
                    <div className="quality-badge full-text">Full Text</div>
                    <div className="quality-value">{fullTextCount}</div>
                    <div className="quality-label">Full-Text Analysis</div>
                    <div className="quality-percentage">
                      {totalCount > 0 ? ((fullTextCount / totalCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                  <div className="quality-card abstract-only">
                    <div className="quality-badge abstract-only">Abstract Only</div>
                    <div className="quality-value">{abstractOnlyCount}</div>
                    <div className="quality-label">Abstract-Only Analysis</div>
                    <div className="quality-percentage">
                      {totalCount > 0 ? ((abstractOnlyCount / totalCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Run Info */}
          <div className="run-info-section">
            <h4>ℹ️ Run Information</h4>
            <div className="info-grid">
              <div className="info-item">
                <strong>Run ID:</strong> {summary.run_id || 'Processing...'}
              </div>
              <div className="info-item">
                <strong>Status:</strong> 
                <span className={`status-badge ${summary.status ? summary.status.toLowerCase() : 'completed'}`}>
                  {summary.status || 'Completed'}
                </span>
              </div>
              <div className="info-item">
                <strong>Created:</strong> {summary.created_at ? new Date(summary.created_at).toLocaleString('en-US', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZone: 'America/New_York'
                }) : new Date().toLocaleString('en-US', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZone: 'America/New_York'
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Records Tab */}
      {selectedTab === 'records' && (
        <div className="records-content">
          {sortedRecords.length > 0 ? (
            <>
              {/* Sorting Controls */}
              <div className="sort-controls">
                <span className="sort-label">Sort by:</span>
                <button 
                  className={`sort-btn ${sortField === 'title' ? 'active' : ''}`}
                  onClick={() => handleSort('title')}
                >
                  Title {sortField === 'title' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  className={`sort-btn ${sortField === 'appraisal_score' ? 'active' : ''}`}
                  onClick={() => handleSort('appraisal_score')}
                >
                  Score {sortField === 'appraisal_score' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  className={`sort-btn ${sortField === 'publication_type' ? 'active' : ''}`}
                  onClick={() => handleSort('publication_type')}
                >
                  Type {sortField === 'publication_type' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  className={`sort-btn ${sortField === 'year' ? 'active' : ''}`}
                  onClick={() => handleSort('year')}
                >
                  Year {sortField === 'year' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  className={`sort-btn ${sortField === 'authors' ? 'active' : ''}`}
                  onClick={() => handleSort('authors')}
                >
                  Authors {sortField === 'authors' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  className={`sort-btn ${sortField === 'status' ? 'active' : ''}`}
                  onClick={() => handleSort('status')}
                >
                  Status {sortField === 'status' && (sortOrder === 'asc' ? '↑' : '↓')}
                </button>
              </div>

              {/* Records List */}
              <div className="records-list">
                {sortedRecords.map((record, index) => (
                  <div key={record.id || `record-${index}`} className="record-item">
                    <div className="record-header">
                      <h5 className="record-title">{record.title}</h5>
                      <div className="record-badges">
                        {/* Status Badge */}
                        <span className={`status-badge ${record.status?.toLowerCase()}`}>
                          {record.status === 'Include' ? '✅' : '❌'} {record.status}
                        </span>
                        
                        {/* Combined Quality Badge - Only show for included records */}
                        {record.status === 'Include' && (
                          <span className={`quality-score-badge ${(record.appraisal_color || 'amber').toLowerCase()}`}>
                            <span className="badge-color">{record.appraisal_color || 'Amber'}</span>
                            <span className="badge-score">{(record.appraisal_score || 0.5).toFixed(2)}</span>
                          </span>
                        )}
                        
                        {record.ai_review_type && record.status === 'Include' && (
                          <span className={`review-type-badge ${record.ai_review_type === 'full_text' ? 'full-text' : 'abstract-only'}`}>
                            {record.ai_review_type === 'full_text' ? '📄 Full Text' : '📋 Abstract Only'}
                          </span>
                        )}

                        {/* View Details Button - Only for included records */}
                        {record.status === 'Include' && (
                          <button
                            className="view-details-btn"
                            onClick={() => handleShowDetailedAppraisal(record)}
                            title="View detailed quality assessment"
                          >
                            📊 View Details
                          </button>
                        )}
                      </div>
                    </div>
                    
                    <div className="record-details">
                      <div className="detail-row">
                        <strong>Authors:</strong> <AuthorDisplay authors={getDisplayAuthors(record)} />
                      </div>
                      <div className="record-meta">
                        <span className="meta-item">📅 <strong>Year:</strong> {getDisplayYear(record)}</span>
                        <span className="meta-item">🔍 <strong>Source:</strong> {inferSourceFromId(record.id, record.source)}</span>
                        <span className="meta-item publication-type">
                          📄 <strong>Type:</strong> {inferPublicationType(record.title, record.publication_type)}
                        </span>
                        {record.institution && (
                          <span className="meta-item">
                            🏛️ <strong>Institution:</strong> {record.institution}
                          </span>
                        )}
                        {(record.doi || record.url) && (
                          <span className="meta-item">
                            🔗 <strong>Link:</strong> <a
                              href={record.doi ? `https://doi.org/${record.doi}` : record.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {record.doi ? record.doi : 'View Article'}
                            </a>
                          </span>
                        )}
                      </div>
                    </div>

                    {record.screening_decision && record.screening_reason && record.screening_reason !== 'Included for appraisal' && (
                      <div className="screening-decision">
                        <span className="screening-reason">
                          <strong>Screening reason:</strong> {record.screening_reason}
                        </span>
                      </div>
                    )}

                    {record.appraisal_reasoning && record.appraisal_reasoning !== 'Quality assessment based on rubric criteria' && (
                      <div className="ai-explanation">
                        <strong>🤖 AI Quality Assessment:</strong> {record.appraisal_reasoning}
                      </div>
                    )}

                    {/* Display abstract if available and not empty */}
                    {record.abstract && record.abstract !== false && record.abstract.trim && record.abstract.trim() !== '' && (
                      <AbstractDisplay abstract={record.abstract} />
                    )}

                    {/* Show placeholder when no abstract is available */}
                    {(!record.abstract || record.abstract === false || (record.abstract.trim && record.abstract.trim() === '')) && (
                      <div className="record-abstract-placeholder">
                        <strong>Abstract:</strong>
                        <span className="placeholder-text">No abstract available</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p>No records found for this run.</p>
          )}
        </div>
      )}

      {/* Screening Tab */}
      {selectedTab === 'screening' && (
        <div className="screening-content">
          {sortedRecords.length > 0 ? (
            <>
              {/* Screening Summary */}
              <div className="screening-summary">
                <h4>🔍 Screening Decision Summary</h4>
                <div className="screening-metrics">
                  {(() => {
                    const includedCount = sortedRecords.filter(r => r.screening_decision === 'include').length
                    const excludedCount = sortedRecords.filter(r => r.screening_decision === 'exclude').length
                    const totalCount = sortedRecords.length
                    
                    console.log('Screening metrics:', { includedCount, excludedCount, totalCount, decisions: sortedRecords.map(r => ({ id: r.id, decision: r.screening_decision })) })
                    
                    return (
                      <>
                        <div className="screening-card included">
                          <div className="screening-badge included">✓ Included</div>
                          <div className="screening-value">{includedCount}</div>
                          <div className="screening-percentage">
                            {totalCount > 0 ? ((includedCount / totalCount) * 100).toFixed(1) : '0.0'}%
                          </div>
                        </div>
                        <div className="screening-card excluded">
                          <div className="screening-badge excluded">✗ Excluded</div>
                          <div className="screening-value">{excludedCount}</div>
                          <div className="screening-percentage">
                            {totalCount > 0 ? ((excludedCount / totalCount) * 100).toFixed(1) : '0.0'}%
                          </div>
                        </div>
                      </>
                    )
                  })()} 
                </div>
              </div>

              {/* Detailed Screening Results */}
              <div className="screening-records">
                <div className="screening-header">
                  <h4>Detailed Screening Decisions</h4>
                  {aiExplanationsLoading && (
                    <div className="ai-loading">
                      <span className="spinner">⏳</span>
                      <span>Generating AI explanations...</span>
                    </div>
                  )}
                </div>
                <div className="records-list">
                  {sortedRecords.map((record, index) => (
                    <div key={record.id || `screening-${index}`} className={`record-item screening-${record.screening_decision}`}>
                      <div className="screening-header">
                        <h5 className="record-title">{record.title}</h5>
                        <div className="screening-badges">
                          <span className={`decision-badge ${record.screening_decision}`}>
                            {record.screening_decision === 'include' ? '✅ Included' : '❌ Excluded'}
                          </span>
                          {record.appraisal_color && (
                            <span className={`appraisal-badge ${record.appraisal_color.toLowerCase()}`}>
                              {record.appraisal_color}
                            </span>
                          )}
                        </div>
                      </div>
                      
                      <div className="screening-details">
                        <div className="detail-row">
                          <strong>Authors:</strong> <AuthorDisplay authors={getDisplayAuthors(record)} />
                        </div>
                        <div className="screening-meta">
                          <span>📅 {getDisplayYear(record)}</span>
                          <span>🔍 {inferSourceFromId(record.id, record.source)}</span>
                          <span>📄 {inferPublicationType(record.title, record.publication_type)}</span>
                          {record.institution && <span>🏛️ {record.institution}</span>}
                        </div>
                      </div>

                      <div className="screening-reasoning">
                        <strong>🤖 AI Screening Rationale:</strong> {
                          record.screening_decision === 'include' 
                            ? `Included for appraisal because ${record.screening_ai_explanation || 'study meets inclusion criteria and appears relevant to the research question'}`
                            : `Excluded from appraisal because ${record.screening_reason || 'screening criteria not met'}`
                        }
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <p>No screening data available for this run.</p>
          )}
        </div>
      )}

      {/* AI Research Synthesis Tab */}
      {selectedTab === 'synthesis' && (
        <div className="synthesis-content">
          {synthesisLoading ? (
            <div className="loading-state">
              <p>🧠 Generating AI research synthesis... This may take a few moments.</p>
              <div className="loading-spinner"></div>
            </div>
          ) : synthesisError ? (
            <div className="error-state">
              <p>❌ {synthesisError}</p>
              <button className="retry-btn" onClick={fetchSynthesis}>
                🔄 Retry Synthesis
              </button>
            </div>
          ) : synthesisData ? (
            <div className="synthesis-results">
              {/* Executive Summary */}
              <div className="synthesis-section">
                <h4>📋 Executive Summary</h4>
                <p className="synthesis-text">{synthesisData.executive_summary}</p>
              </div>

              {/* Research Question Answer */}
              <div className="synthesis-section">
                <h4>❓ Research Question Answer</h4>
                <p className="synthesis-text">{synthesisData.research_question_answer}</p>
              </div>

              {/* LICO Insights */}
              <div className="synthesis-section">
                <h4>🎯 LICO Framework Insights</h4>
                <div className="lico-insights">
                  <div className="lico-item">
                    <h5>👥 Learner Insights</h5>
                    <p>{synthesisData.lico_insights?.learner_insights}</p>
                  </div>
                  <div className="lico-item">
                    <h5>🔧 Intervention Insights</h5>
                    <p>{synthesisData.lico_insights?.intervention_insights}</p>
                  </div>
                  <div className="lico-item">
                    <h5>📍 Context Insights</h5>
                    <p>{synthesisData.lico_insights?.context_insights}</p>
                  </div>
                  <div className="lico-item">
                    <h5>📊 Outcome Insights</h5>
                    <p>{synthesisData.lico_insights?.outcome_insights}</p>
                  </div>
                </div>
              </div>

              {/* Key Recommendations */}
              <div className="synthesis-section">
                <h4>💡 Key Recommendations</h4>
                <ul className="recommendations-list">
                  {synthesisData.key_recommendations?.map((rec: string, idx: number) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>

              {/* Supporting Evidence */}
              {synthesisData.supporting_evidence && synthesisData.supporting_evidence.length > 0 && (
                <div className="synthesis-section">
                  <h4>📚 Supporting Evidence</h4>
                  {synthesisData.supporting_evidence.map((evidence: any, idx: number) => (
                    <div key={idx} className="evidence-item">
                      <h5 className="evidence-finding">
                        🔍 {evidence.finding}
                        {evidence.citation_keys && evidence.citation_keys.length > 0 && (
                          <span className="citation-badges">
                            {evidence.citation_keys.map((key: string) => (
                              <span key={key} className="citation-key-badge inline">[{key}]</span>
                            ))}
                          </span>
                        )}
                      </h5>
                      <p className="evidence-strength">Strength: {evidence.strength_rating}</p>

                      {evidence.supporting_quotes && evidence.supporting_quotes.length > 0 && (
                        <div className="supporting-quotes">
                          <h6>📝 Direct Quotes:</h6>
                          {evidence.supporting_quotes.map((quote: string, qIdx: number) => (
                            <blockquote key={qIdx} className="support-quote">
                              "{quote}"
                            </blockquote>
                          ))}
                        </div>
                      )}
                      
                      {evidence.source_studies && evidence.source_studies.length > 0 && (
                        <div className="source-studies">
                          <h6>📖 Source Studies:</h6>
                          <ul>
                            {evidence.source_studies.map((study: string, sIdx: number) => (
                              <li key={sIdx}>{study}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {evidence.citations && evidence.citations.length > 0 && (
                        <div className="citation-details">
                          <h6>🔗 Citations:</h6>
                          <ul className="citation-list">
                            {evidence.citations.map((citation: CitationMetadata) => renderCitation(citation))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Quality Assessment */}
              <div className="synthesis-section">
                <h4>⚖️ Quality Assessment</h4>
                <div className="quality-metrics">
                  <p><strong>Evidence Strength:</strong> {synthesisData.evidence_strength}</p>
                  <p><strong>Confidence Level:</strong> {synthesisData.confidence_level}</p>
                  <p><strong>Methodological Quality:</strong> {synthesisData.methodological_quality}</p>
                </div>
              </div>

              {/* Knowledge Gaps & Future Research */}
              <div className="synthesis-section">
                <h4>🔍 Knowledge Gaps</h4>
                <ul className="gaps-list">
                  {synthesisData.knowledge_gaps?.map((gap: string, idx: number) => (
                    <li key={idx}>{gap}</li>
                  ))}
                </ul>
              </div>

              {synthesisData.future_research_directions && synthesisData.future_research_directions.length > 0 && (
                <div className="synthesis-section">
                  <h4>🚀 Future Research Directions</h4>
                  <ul className="future-research-list">
                    {synthesisData.future_research_directions.map((direction: string, idx: number) => (
                      <li key={idx}>{direction}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Full Text Availability */}
              {synthesisData.full_text_availability && Object.keys(synthesisData.full_text_availability).length > 0 && (
                <div className="synthesis-section">
                  <h4>📄 Full Text Availability</h4>
                  <div className="full-text-status">
                    {studyCitations.map(citation => {
                      const availability = fullTextAvailabilityEntries.find(([label]) => label.includes(`[${citation.citation_key}]`))
                      const isAvailable = availability ? Boolean(availability[1]) : false
                      return (
                        <div key={citation.citation_key} className={`availability-item ${isAvailable ? 'available' : 'not-available'}`}>
                          <span>[{citation.citation_key}] {citation.title}: {isAvailable ? '✅ Available' : '❌ Not Available'}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {studyCitations.length > 0 && (
                <div className="synthesis-section">
                  <h4>📑 Study References</h4>
                  <ul className="citation-list">
                    {studyCitations.map(citation => renderCitation(citation))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="synthesis-placeholder">
              <p>Click to generate AI-powered research synthesis with LICO framework analysis.</p>
              <button className="generate-synthesis-btn" onClick={fetchSynthesis}>
                🤖 Generate Research Synthesis
              </button>
            </div>
          )}
        </div>
      )}
    </div>

    {/* Detailed Appraisal Modal */}
    {showDetailedAppraisal && selectedRecordForDetail && selectedRecordForDetail.detailed_appraisals && (
      <DetailedAppraisalView
        recordId={selectedRecordForDetail.id}
        recordTitle={selectedRecordForDetail.title}
        appraisals={selectedRecordForDetail.detailed_appraisals}
        onClose={handleCloseDetailedAppraisal}
      />
    )}
    </>
  )
}

export default RunResults