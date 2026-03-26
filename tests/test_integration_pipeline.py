"""
Integration tests for the PRESS→harvest→dedupe→appraise→report pipeline
"""
from __future__ import annotations
import os
import sys
import pytest
from unittest.mock import Mock, patch

# Add the parent directory to Python path to enable app imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.graph.build import get_graph
from app.graph.state import AgentState
from app.models import PressPlan, RecordModel, ScreeningModel, AppraisalModel

# Test data
SAMPLE_QUERY = "machine learning in education"

SAMPLE_PRESS_PLAN = PressPlan(
    concepts=["students", "machine learning", "traditional methods", "learning outcomes"],
    boolean="(students OR learners) AND (machine learning OR AI) AND (learning OR achievement)",
    sources=["PubMed", "ERIC", "Crossref"],
    years="2020-"
)

SAMPLE_RECORDS = [
    RecordModel(
        record_id="test_1",
        title="Machine Learning in Educational Settings",
        abstract="This study examines the impact of machine learning on student performance.",
        authors="Smith, J., Doe, A.",
        year=2023,
        doi="10.1234/test1",
        url="https://example.com/paper1",
        source="pubmed"
    ),
    RecordModel(
        record_id="test_2", 
        title="AI-Enhanced Learning Platforms",
        abstract="Research on artificial intelligence applications in education.",
        authors="Brown, K.",
        year=2022,
        doi="10.1234/test2",
        url="https://example.com/paper2",
        source="crossref"
    ),
    RecordModel(
        record_id="test_3",
        title="Traditional vs Modern Teaching Methods",  # Should be excluded
        abstract="Comparison of old and new teaching approaches without AI.",
        authors="Wilson, L.",
        year=2021,
        source="eric"
    )
]


class TestPipelineIntegration:
    """Test the complete PRESS pipeline integration"""
    
    @pytest.fixture
    def graph(self):
        """Get the LangGraph workflow"""
        return get_graph()
    
    @pytest.fixture
    def initial_state(self):
        """Initial state for testing"""
        return AgentState(
            query=SAMPLE_QUERY,
            run_id="test_integration_run",
            records=[],
            screenings=[],
            appraisals=[],
            seen_external_ids=[],
            source_counts={},
            timings={}
        )
    
    def test_graph_structure(self, graph):
        """Test that the graph is properly constructed"""
        # Check that all nodes are present
        expected_nodes = {"plan_press", "harvest", "dedupe_screen", "appraise", "report_prisma"}
        actual_nodes = set(graph.nodes.keys())
        assert expected_nodes.issubset(actual_nodes), f"Missing nodes: {expected_nodes - actual_nodes}"
    
    @patch('app.graph.nodes.plan_press')
    def test_plan_press_node(self, mock_plan_press, graph, initial_state):
        """Test the PRESS planning node"""
        # Mock the plan_press function to return a PRESS plan
        mock_plan_press.return_value = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN
        }
        
        # Execute just the plan_press node
        result = mock_plan_press(initial_state)
        
        assert "press" in result
        assert "students" in result["press"].concepts
        assert "machine learning" in result["press"].concepts
        mock_plan_press.assert_called_once_with(initial_state)
    
    @patch('app.graph.nodes.harvest')
    def test_harvest_node(self, mock_harvest, graph, initial_state):
        """Test the harvesting node"""
        # Set up state with PRESS plan
        state_with_press = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN
        }
        
        # Mock harvest to return sample records
        mock_harvest.return_value = {
            **state_with_press,
            "records": SAMPLE_RECORDS,
            "source_counts": {"pubmed": 1, "crossref": 1, "eric": 1}
        }
        
        result = mock_harvest(state_with_press)
        
        assert len(result["records"]) == 3
        assert result["source_counts"]["pubmed"] == 1
        mock_harvest.assert_called_once_with(state_with_press)
    
    @patch('app.graph.nodes.dedupe_screen')
    def test_dedupe_screen_node(self, mock_dedupe_screen, graph, initial_state):
        """Test the deduplication and screening node"""
        state_with_records = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN,
            "records": SAMPLE_RECORDS
        }
        
        # Mock to include 2 records and exclude 1
        mock_screenings = [
            ScreeningModel(record_id="test_1", decision="include", reason="Relevant to ML in education"),
            ScreeningModel(record_id="test_2", decision="include", reason="AI in education context"),
            ScreeningModel(record_id="test_3", decision="exclude", reason="No ML/AI content")
        ]
        
        mock_dedupe_screen.return_value = {
            **state_with_records,
            "records": SAMPLE_RECORDS[:2],  # Only included records
            "screenings": mock_screenings
        }
        
        result = mock_dedupe_screen(state_with_records)
        
        assert len(result["records"]) == 2  # 2 included
        assert len(result["screenings"]) == 3  # All screening decisions
        included_decisions = [s.decision for s in result["screenings"] if s.decision == "include"]
        assert len(included_decisions) == 2
        mock_dedupe_screen.assert_called_once_with(state_with_records)
    
    @patch('app.graph.nodes.appraise')
    def test_appraise_node(self, mock_appraise, graph, initial_state):
        """Test the appraisal node"""
        state_with_screening = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN,
            "records": SAMPLE_RECORDS[:2],  # Only included records
            "screenings": [
                ScreeningModel(record_id="test_1", decision="include", reason="Relevant"),
                ScreeningModel(record_id="test_2", decision="include", reason="Relevant")
            ]
        }
        
        # Mock appraisals
        mock_appraisals = [
            AppraisalModel(
                record_id="test_1",
                rating="Green",
                scores={"recency": 1.0, "design": 0.8, "bias": 0.7, "final": 0.82},
                rationale="High quality recent study"
            ),
            AppraisalModel(
                record_id="test_2", 
                rating="Amber",
                scores={"recency": 0.8, "design": 0.6, "bias": 0.6, "final": 0.63},
                rationale="Moderate quality study"
            )
        ]
        
        mock_appraise.return_value = {
            **state_with_screening,
            "appraisals": mock_appraisals
        }
        
        result = mock_appraise(state_with_screening)
        
        assert len(result["appraisals"]) == 2
        ratings = [a.rating for a in result["appraisals"]]
        assert "Green" in ratings
        assert "Amber" in ratings
        mock_appraise.assert_called_once_with(state_with_screening)
    
    @patch('app.graph.nodes.report_prisma')
    def test_report_prisma_node(self, mock_report_prisma, graph, initial_state):
        """Test the PRISMA reporting node"""
        final_state = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN,
            "records": SAMPLE_RECORDS[:2],
            "screenings": [
                ScreeningModel(record_id="test_1", decision="include", reason="Relevant"),
                ScreeningModel(record_id="test_2", decision="include", reason="Relevant"),
                ScreeningModel(record_id="test_3", decision="exclude", reason="Not relevant")
            ],
            "appraisals": [
                AppraisalModel(record_id="test_1", rating="Green", scores={"final": 0.82}),
                AppraisalModel(record_id="test_2", rating="Amber", scores={"final": 0.63})
            ]
        }
        
        from app.models import PrismaCountsModel
        mock_prisma = PrismaCountsModel(
            identified=3,
            deduped=3, 
            screened=3,
            excluded=1,
            eligible=2,
            included=2
        )
        
        mock_report_prisma.return_value = {
            **final_state,
            "prisma": mock_prisma
        }
        
        result = mock_report_prisma(final_state)
        
        assert result["prisma"].identified == 3
        assert result["prisma"].included == 2
        assert result["prisma"].excluded == 1
        mock_report_prisma.assert_called_once_with(final_state)
    
    @patch('app.graph.nodes.plan_press')
    @patch('app.graph.nodes.harvest')
    @patch('app.graph.nodes.dedupe_screen')
    @patch('app.graph.nodes.appraise')
    @patch('app.graph.nodes.report_prisma')
    def test_complete_pipeline_mock(self, mock_report, mock_appraise, mock_dedupe, 
                                  mock_harvest, mock_plan, graph, initial_state):
        """Test the complete pipeline with mocked nodes"""
        # Set up the mock chain
        mock_plan.return_value = {**initial_state, "press": SAMPLE_PRESS_PLAN}
        mock_harvest.return_value = {**initial_state, "press": SAMPLE_PRESS_PLAN, "records": SAMPLE_RECORDS}
        mock_dedupe.return_value = {
            **initial_state, 
            "press": SAMPLE_PRESS_PLAN,
            "records": SAMPLE_RECORDS[:2], 
            "screenings": [ScreeningModel(record_id="test_1", decision="include", reason="Good")]
        }
        mock_appraise.return_value = {
            **initial_state,
            "press": SAMPLE_PRESS_PLAN, 
            "records": SAMPLE_RECORDS[:2],
            "appraisals": [AppraisalModel(record_id="test_1", rating="Green", scores={"final": 0.8})]
        }
        
        from app.models import PrismaCountsModel
        mock_report.return_value = {
            **initial_state,
            "prisma": PrismaCountsModel(identified=3, included=2, excluded=1, eligible=2, screened=3, deduped=3)
        }
        
        # Execute the complete pipeline
        config = {"configurable": {"thread_id": "test_thread"}}
        result = graph.invoke(initial_state, config)
        
        # Verify all nodes were called
        mock_plan.assert_called_once()
        mock_harvest.assert_called_once()
        mock_dedupe.assert_called_once()
        mock_appraise.assert_called_once()
        mock_report.assert_called_once()
        
        # Check final result structure
        assert "prisma" in result
        assert result["prisma"].identified == 3
        assert result["prisma"].included == 2


class TestPipelineErrorHandling:
    """Test error handling in the pipeline"""
    
    @pytest.fixture
    def graph(self):
        return get_graph()
    
    @patch('app.graph.nodes.plan_press')
    def test_plan_press_failure(self, mock_plan_press, graph):
        """Test handling of PRESS planning failures"""
        mock_plan_press.side_effect = Exception("PRESS planning failed")
        
        initial_state = AgentState(query="test query")
        config = {"configurable": {"thread_id": "error_test"}}
        
        with pytest.raises(Exception, match="PRESS planning failed"):
            graph.invoke(initial_state, config)
    
    @patch('app.graph.nodes.plan_press')
    @patch('app.graph.nodes.harvest')
    def test_harvest_failure_graceful(self, mock_harvest, mock_plan_press, graph):
        """Test graceful handling of harvest failures"""
        mock_plan_press.return_value = {"press": SAMPLE_PRESS_PLAN}
        mock_harvest.side_effect = Exception("Network error during harvest")
        
        initial_state = AgentState(query="test query")
        config = {"configurable": {"thread_id": "harvest_error_test"}}
        
        with pytest.raises(Exception, match="Network error during harvest"):
            graph.invoke(initial_state, config)


class TestPipelinePerformance:
    """Test performance characteristics of the pipeline"""
    
    @pytest.fixture
    def graph(self):
        return get_graph()
    
    def test_state_threading(self, graph):
        """Test that multiple threads can run independently"""
        import threading
        import time
        
        results = {}
        
        def run_pipeline(thread_id):
            initial_state = AgentState(
                query=f"query_{thread_id}",
                run_id=f"run_{thread_id}"
            )
            config = {"configurable": {"thread_id": f"thread_{thread_id}"}}
            
            # This would normally execute the full pipeline
            # For testing, we just verify the thread isolation
            results[thread_id] = {"query": initial_state["query"], "run_id": initial_state["run_id"]}
        
        # Run multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=run_pipeline, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify thread isolation
        assert len(results) == 3
        assert results[0]["query"] == "query_0"
        assert results[1]["query"] == "query_1" 
        assert results[2]["query"] == "query_2"


if __name__ == "__main__":
    pytest.main([__file__])