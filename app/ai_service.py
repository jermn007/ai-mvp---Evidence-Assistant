# app/ai_service.py
"""
AI-powered assistance for systematic literature reviews.
Provides intelligent suggestions for PRESS planning, quality assessment, and literature analysis.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.press_contract import LICO

logger = logging.getLogger(__name__)

# Response models for structured AI outputs
class LICOEnhancement(BaseModel):
    """Enhanced LICO terms with AI suggestions"""
    learner_suggestions: List[str] = Field(description="Related learner terms and synonyms")
    intervention_suggestions: List[str] = Field(description="Related intervention terms and synonyms")
    context_suggestions: List[str] = Field(description="Related context terms and synonyms")
    outcome_suggestions: List[str] = Field(description="Related outcome terms and synonyms")
    mesh_suggestions: Dict[str, List[str]] = Field(description="Recommended MeSH terms by category")
    template_recommendation: str = Field(description="Recommended template: clinical, education, or general")
    explanation: str = Field(description="Reasoning behind the suggestions")

class PressStrategyAnalysis(BaseModel):
    """Analysis of a PRESS search strategy"""
    completeness_score: float = Field(description="Score from 0-1 for strategy completeness")
    balance_assessment: str = Field(description="Assessment of search term balance")
    suggestions: List[str] = Field(description="Specific improvement suggestions")
    missing_components: List[str] = Field(description="Missing LICO components or terms")
    estimated_precision: str = Field(description="Estimated search precision: high, medium, low")
    estimated_recall: str = Field(description="Estimated search recall: high, medium, low")

class StudyRelevanceAssessment(BaseModel):
    """AI assessment of study relevance"""
    relevance_score: float = Field(description="Relevance score from 0-1")
    inclusion_recommendation: str = Field(description="include, exclude, or uncertain")
    reasoning: str = Field(description="Detailed reasoning for the recommendation")
    key_factors: List[str] = Field(description="Key factors influencing the decision")
    exclusion_reason: Optional[str] = Field(description="Specific exclusion reason if applicable")

@dataclass
class AIConfig:
    """Configuration for AI service"""
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 2000
    max_retries: int = 3

class AIService:
    """Service for AI-powered systematic review assistance"""
    
    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or AIConfig()
        
        # Use centralized LLM factory instead of direct ChatOpenAI
        from app.llm_factory import get_llm_factory
        self._factory = get_llm_factory()
        
        # Configure LangSmith if enabled
        if self._factory.settings.enable_langsmith:
            logger.info("LangSmith observability enabled for AI service")
    
    def is_available(self) -> bool:
        """Check if AI service is available"""
        return self._factory.is_available()
    
    def _get_model(self, task_type: str = "smart"):
        """Get appropriate model for the task"""
        if task_type == "fast":
            return self._factory.get_fast_model(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
        else:
            return self._factory.get_smart_model(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
    
    async def enhance_lico_terms(self, lico: LICO, research_domain: Optional[str] = None) -> Optional[LICOEnhancement]:
        """
        Enhance LICO terms with AI-generated suggestions for better search coverage.
        
        Args:
            lico: Original LICO terms
            research_domain: Optional domain context (e.g., "nursing education", "medical training")
        
        Returns:
            Enhanced LICO suggestions or None if AI unavailable
        """
        if not self.is_available():
            return None
        
        # Create domain-aware prompt
        domain_context = f" in the context of {research_domain}" if research_domain else ""
        
        system_prompt = """You are an expert systematic review librarian and search strategist. 
        Your task is to enhance LICO (Learner, Intervention, Context, Outcome) terms for comprehensive literature searching.
        
        For each LICO component provided, suggest:
        1. Synonyms and related terms
        2. Alternative spellings and variants
        3. Broader and narrower terms
        4. Relevant MeSH headings where applicable
        
        Consider both controlled vocabulary (MeSH) and free text terms.
        Focus on maximizing recall while maintaining precision.
        """
        
        human_prompt = f"""Please enhance these LICO terms for a systematic literature review{domain_context}:

        Learner: {lico.learner or 'Not specified'}
        Intervention: {lico.intervention or 'Not specified'}
        Context: {lico.context or 'Not specified'}
        Outcome: {lico.outcome or 'Not specified'}

        Provide comprehensive suggestions for each component, including:
        - Related terms and synonyms
        - MeSH headings where applicable
        - Template recommendation (clinical, education, or general)
        - Explanation of your reasoning

        Format your response as valid JSON matching the LICOEnhancement schema."""
        
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", human_prompt)
            ])
            
            parser = JsonOutputParser(pydantic_object=LICOEnhancement)
            model = self._get_model("smart")
            chain = prompt | model | parser
            
            result = await chain.ainvoke({})
            return LICOEnhancement(**result) if isinstance(result, dict) else result
            
        except Exception as e:
            logger.error(f"Error enhancing LICO terms: {e}")
            return None
    
    async def analyze_press_strategy(self, strategy_lines: List[Dict[str, Any]]) -> Optional[PressStrategyAnalysis]:
        """
        Analyze a PRESS search strategy and provide improvement suggestions.
        
        Args:
            strategy_lines: List of strategy line dictionaries with 'type' and 'text' fields
        
        Returns:
            Strategy analysis or None if AI unavailable
        """
        if not self.is_available():
            return None
        
        # Format strategy lines for analysis
        strategy_text = ""
        for i, line in enumerate(strategy_lines, 1):
            strategy_text += f"{i}. [{line.get('type', 'Unknown')}] {line.get('text', '')}\n"
        
        system_prompt = """You are an expert in systematic review search methodology and PRESS guidelines.
        Analyze the provided search strategy for completeness, balance, and potential improvements.
        
        Consider:
        - LICO component coverage (Learner, Intervention, Context, Outcome)
        - Balance between sensitivity (recall) and precision
        - Use of controlled vocabulary (MeSH) vs. free text
        - Boolean logic structure
        - Potential gaps or redundancies
        """
        
        human_prompt = f"""Please analyze this PRESS search strategy:

        {strategy_text}

        Provide a comprehensive analysis including:
        - Completeness score (0-1)
        - Balance assessment
        - Specific improvement suggestions
        - Missing components
        - Estimated precision and recall levels

        Format your response as valid JSON matching the PressStrategyAnalysis schema."""
        
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", human_prompt)
            ])
            
            parser = JsonOutputParser(pydantic_object=PressStrategyAnalysis)
            model = self._get_model("smart")
            chain = prompt | model | parser
            
            result = await chain.ainvoke({})
            return PressStrategyAnalysis(**result) if isinstance(result, dict) else result
            
        except Exception as e:
            logger.error(f"Error analyzing PRESS strategy: {e}")
            return None
    
    async def assess_study_relevance(
        self, 
        title: str, 
        abstract: Optional[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        research_question: Optional[str] = None
    ) -> Optional[StudyRelevanceAssessment]:
        """
        Assess the relevance of a study for inclusion in a systematic review.
        
        Args:
            title: Study title
            abstract: Study abstract
            inclusion_criteria: List of inclusion criteria
            exclusion_criteria: List of exclusion criteria
            research_question: Optional research question for context
        
        Returns:
            Relevance assessment or None if AI unavailable
        """
        if not self.is_available():
            return None
        
        system_prompt = """You are an expert systematic reviewer conducting title and abstract screening.
        Your task is to assess whether a study meets the inclusion criteria for a systematic review.
        
        Be thorough but efficient in your assessment. Consider:
        - Alignment with research question and objectives
        - Population, intervention, comparator, outcome (PICO) match
        - Study design appropriateness
        - Clear reasons for inclusion or exclusion
        """
        
        criteria_text = ""
        if inclusion_criteria:
            criteria_text += "INCLUSION CRITERIA:\n" + "\n".join(f"- {c}" for c in inclusion_criteria) + "\n\n"
        if exclusion_criteria:
            criteria_text += "EXCLUSION CRITERIA:\n" + "\n".join(f"- {c}" for c in exclusion_criteria) + "\n\n"
        
        research_context = f"RESEARCH QUESTION: {research_question}\n\n" if research_question else ""
        
        human_prompt = f"""{research_context}{criteria_text}Please assess this study for inclusion:

        TITLE: {title}

        ABSTRACT: {abstract or 'No abstract provided'}

        Provide your assessment including:
        - Relevance score (0-1)
        - Inclusion recommendation (include/exclude/uncertain)
        - Detailed reasoning
        - Key factors that influenced your decision
        - Specific exclusion reason if applicable

        Format your response as valid JSON matching the StudyRelevanceAssessment schema."""
        
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", human_prompt)
            ])
            
            parser = JsonOutputParser(pydantic_object=StudyRelevanceAssessment)
            model = self._get_model("smart")
            chain = prompt | model | parser
            
            result = await chain.ainvoke({})
            return StudyRelevanceAssessment(**result) if isinstance(result, dict) else result
            
        except Exception as e:
            logger.error(f"Error assessing study relevance: {e}")
            return None
    
    def suggest_template(self, lico: LICO) -> str:
        """
        Suggest the best template based on LICO content analysis.
        
        Args:
            lico: LICO terms to analyze
        
        Returns:
            Template name: "clinical", "education", or "general"
        """
        combined_text = f"{lico.learner or ''} {lico.intervention or ''} {lico.context or ''} {lico.outcome or ''}".lower()
        
        # Education indicators
        education_terms = [
            "student", "education", "curriculum", "teaching", "learning", "training", 
            "academic", "school", "university", "college", "instructor", "faculty",
            "classroom", "course", "lecture", "simulation", "competency", "skill",
            "nursing student", "medical student", "resident", "trainee", "pregraduate"
        ]
        
        # Clinical indicators  
        clinical_terms = [
            "patient", "clinical", "hospital", "healthcare", "treatment", "therapy",
            "diagnosis", "medicine", "intervention", "care", "health outcome",
            "medical", "surgical", "nursing", "physician", "practitioner",
            "bedside", "ward", "clinic", "emergency", "intensive care"
        ]
        
        education_score = sum(1 for term in education_terms if term in combined_text)
        clinical_score = sum(1 for term in clinical_terms if term in combined_text)
        
        # Determine template based on scores
        if education_score > clinical_score and education_score >= 2:
            return "education"
        elif clinical_score > education_score and clinical_score >= 2:
            return "clinical"
        else:
            return "general"
    
    async def generate_quality_rationale(
        self, 
        title: str, 
        abstract: Optional[str],
        year: Optional[int],
        rating: str,
        scores: Dict[str, float]
    ) -> Optional[str]:
        """
        Generate detailed rationale for a quality assessment rating.
        
        Args:
            title: Study title
            abstract: Study abstract
            year: Publication year
            rating: Quality rating (Red/Amber/Green)
            scores: Individual component scores
        
        Returns:
            Detailed rationale text or None if AI unavailable
        """
        if not self.is_available():
            return None
        
        system_prompt = """You are an expert in study quality assessment for systematic reviews.
        Generate clear, concise rationales for quality ratings that explain the key factors 
        contributing to the overall assessment.
        
        Focus on:
        - Study design strengths and limitations
        - Risk of bias considerations
        - Methodological rigor
        - Relevance and applicability
        - Recency and current relevance
        """
        
        scores_text = ""
        for component, score in scores.items():
            if component != "final":
                scores_text += f"- {component.replace('_', ' ').title()}: {score:.2f}\n"
        
        human_prompt = f"""Please generate a quality assessment rationale for this study:

        TITLE: {title}
        ABSTRACT: {abstract or 'No abstract provided'}
        YEAR: {year or 'Unknown'}
        OVERALL RATING: {rating}
        
        COMPONENT SCORES:
        {scores_text}

        Provide a clear, professional rationale (2-3 sentences) explaining why this study 
        received a {rating} rating, highlighting the key factors that influenced the assessment."""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            model = self._get_model("smart")
            response = await model.ainvoke(messages)
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating quality rationale: {e}")
            return None

    async def generate_research_question(self, lico: LICO) -> Optional[str]:
        """
        Generate an academic research question from LICO components.
        
        Args:
            lico: LICO components to convert into research question
            
        Returns:
            Research question string or None if AI unavailable
        """
        if not self.is_available():
            return None
            
        system_prompt = """You are an expert academic researcher and systematic review methodologist.
        Your task is to create well-formed research questions from LICO (Learner, Intervention, Context, Outcome) components.
        
        Guidelines:
        - Generate clear, focused, and answerable research questions
        - Use appropriate academic language and structure
        - Consider systematic review best practices
        - Include all relevant LICO components naturally
        - Make the question specific enough to guide a focused literature search
        """
        
        human_prompt = f"""Create a well-structured research question from these LICO components:

Learner: {lico.learner or 'Not specified'}
Intervention: {lico.intervention or 'Not specified'} 
Context: {lico.context or 'Not specified'}
Outcome: {lico.outcome or 'Not specified'}

Please generate a clear, focused research question that incorporates these components appropriately for a systematic literature review."""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            model = self._get_model("smart")
            response = await model.ainvoke(messages)
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating research question: {e}")
            return None

    async def extract_lico_from_question(self, question: str) -> Optional[LICO]:
        """
        Extract LICO components from a research question.
        
        Args:
            question: Research question to parse
            
        Returns:
            LICO object with extracted components or None if AI unavailable
        """
        if not self.is_available():
            return None
            
        system_prompt = """You are an expert systematic review methodologist.
        Your task is to extract LICO (Learner, Intervention, Context, Outcome) components from research questions.
        
        Guidelines:
        - Learner: Target population, participants, or subjects
        - Intervention: What is being studied, implemented, or tested
        - Context: Setting, environment, or conditions
        - Outcome: Measured results, effects, or endpoints
        - Extract only what is explicitly mentioned or clearly implied
        - Use "Not specified" if a component is not identifiable
        """
        
        human_prompt = f"""Extract the LICO components from this research question:

"{question}"

Please identify and extract:
- Learner (target population): 
- Intervention (what is being studied):
- Context (setting or environment):
- Outcome (measured results):

Format your response as a JSON object with keys: learner, intervention, context, outcome"""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            model = self._get_model("smart")
            response = await model.ainvoke(messages)
            result = json.loads(response.content.strip())
            
            # Clean up and validate the extracted components
            return LICO(
                learner=(result.get("learner") or "").strip() or "",
                intervention=(result.get("intervention") or "").strip() or "",
                context=(result.get("context") or "").strip() or "",
                outcome=(result.get("outcome") or "").strip() or ""
            )
            
        except Exception as e:
            logger.error(f"Error extracting LICO from question: {e}")
            return None

    async def enhance_research_question(self, question: str) -> Optional[str]:
        """
        Enhance and improve a research question for systematic review quality.
        
        Args:
            question: Original research question
            
        Returns:
            Enhanced research question or None if AI unavailable
        """
        if not self.is_available():
            return None
            
        system_prompt = """You are an expert systematic review methodologist and academic researcher.
        Your task is to enhance research questions to meet high academic standards for systematic reviews.
        
        Improvements to consider:
        - Clarity and precision of language
        - Appropriate scope (not too broad or narrow)
        - Inclusion of all relevant LICO components
        - Academic rigor and searchability
        - Alignment with systematic review best practices
        - Clear, answerable focus
        """
        
        human_prompt = f"""Please enhance this research question for a systematic literature review:

Original question: "{question}"

Provide an improved version that:
1. Is clear, focused, and academically rigorous
2. Includes appropriate LICO components where relevant
3. Is suitable for systematic review methodology
4. Maintains the original intent while improving clarity and scope

Enhanced question:"""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            model = self._get_model("smart")
            response = await model.ainvoke(messages)
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Error enhancing research question: {e}")
            return None

# Global service instance
_ai_service = AIService()

def get_ai_service() -> AIService:
    """Get the global AI service instance"""
    return _ai_service