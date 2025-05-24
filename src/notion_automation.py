import streamlit as st
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
import tempfile
from pathlib import Path

from src.notion_watcher import poll_notion_db
from src.notion_research import run_deep_research  
from src.notion_writer import publish_report
from src.notion_scorer import run_project_scoring
from src.notion_pusher import publish_ratings
from src.audit_logger import get_audit_logger

def render_notion_automation_page():
    """Render the Notion automation page"""
    st.header("Notion CRM Integration")
    st.write("Monitor Notion database and run automated research pipelines.")
    
    # Check if required environment variables are set
    import os
    required_env_vars = ["NOTION_TOKEN", "NOTION_DB_ID", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        st.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        st.info("Please set these environment variables to use Notion automation features.")
        return
    
    # Notion Database Monitoring
    st.subheader("1. Notion Database Status")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Check Notion Database", key="check_notion_db"):
            with st.spinner("Checking Notion database..."):
                try:
                    # Get projects from last 7 days
                    completed_after = datetime.now(timezone.utc) - timedelta(days=7)
                    created_after = datetime.now(timezone.utc) - timedelta(days=150)
                    
                    pages = poll_notion_db(
                        last_updated=completed_after,
                        created_after=created_after
                    )
                    
                    st.session_state.notion_pages = pages
                    st.success(f"Found {len(pages)} eligible projects with completed DDQ")
                    
                    get_audit_logger(
                        user=st.session_state.username,
                        role=st.session_state.get("role", "N/A"),
                        action="NOTION_DB_CHECK",
                        details=f"Retrieved {len(pages)} projects from Notion"
                    )
                    
                except Exception as e:
                    st.error(f"Error checking Notion database: {str(e)}")
                    get_audit_logger(
                        user=st.session_state.username,
                        role=st.session_state.get("role", "N/A"),
                        action="NOTION_DB_CHECK_ERROR",
                        details=f"Error checking Notion: {str(e)}"
                    )
    
    with col2:
        # Display last check results
        if hasattr(st.session_state, 'notion_pages'):
            st.info(f"Last check: {len(st.session_state.notion_pages)} projects found")
        else:
            st.info("Click 'Check Notion Database' to get current status")
    
    # Display found projects
    if hasattr(st.session_state, 'notion_pages') and st.session_state.notion_pages:
        st.subheader("2. Eligible Projects")
        
        for i, page in enumerate(st.session_state.notion_pages):
            with st.expander(f"Project: {page.get('title', 'Untitled')} ({page['page_id']})"):
                st.write(f"**Page ID:** {page['page_id']}")
                st.write(f"**Title:** {page.get('title', 'Untitled')}")
                
                # Manual trigger for individual project
                if st.button(f"Run Research Pipeline", key=f"run_pipeline_{i}"):
                    run_individual_pipeline(page)
    
    # Bulk automation controls
    st.subheader("3. Automation Controls")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Run Full Pipeline (All Projects)", key="run_full_pipeline"):
            if hasattr(st.session_state, 'notion_pages') and st.session_state.notion_pages:
                run_full_pipeline(st.session_state.notion_pages)
            else:
                st.warning("Please check Notion database first to get eligible projects")
    
    with col2:
        st.info("Full pipeline includes: Research → Report → Scoring → Ratings")

def run_individual_pipeline(page: Dict[str, str]):
    """Run the full research pipeline for a single project"""
    page_id = page["page_id"]
    title = page.get("title", "Untitled")
    
    with st.spinner(f"Running research pipeline for: {title}"):
        try:
            # Create temporary directory for this run
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                # Step 1: Deep research
                st.write("🔍 Running deep research...")
                md_path = tmp_path / f"research_{page_id}.md"
                report_path = run_deep_research(page_id, md_path)
                st.write("✅ Research completed")
                
                # Step 2: Publish report
                st.write("📝 Publishing report to Notion...")
                notion_url = publish_report(page_id, report_path)
                st.write("✅ Report published")
                
                # Step 3: Generate scores
                st.write("📊 Generating project scores...")
                json_path = run_project_scoring(page_id)
                st.write("✅ Scoring completed")
                
                # Step 4: Publish ratings
                st.write("🏆 Publishing ratings...")
                ratings_db_id = publish_ratings(page_id)
                st.write("✅ Ratings published")
                
                st.success(f"✅ Pipeline completed successfully for: {title}")
                st.info(f"Report URL: {notion_url}")
                
                get_audit_logger(
                    user=st.session_state.username,
                    role=st.session_state.get("role", "N/A"),
                    action="NOTION_PIPELINE_SUCCESS",
                    details=f"Completed full pipeline for project: {title} ({page_id})"
                )
                
        except Exception as e:
            st.error(f"❌ Pipeline failed for {title}: {str(e)}")
            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="NOTION_PIPELINE_ERROR",
                details=f"Pipeline failed for {title}: {str(e)}"
            )

def run_full_pipeline(pages: List[Dict[str, str]]):
    """Run the full research pipeline for all projects"""
    st.write(f"Running pipeline for {len(pages)} projects...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, page in enumerate(pages):
        page_id = page["page_id"]
        title = page.get("title", "Untitled")
        
        status_text.text(f"Processing {i+1}/{len(pages)}: {title}")
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                # Run pipeline steps
                md_path = tmp_path / f"research_{page_id}.md"
                report_path = run_deep_research(page_id, md_path)
                notion_url = publish_report(page_id, report_path)
                json_path = run_project_scoring(page_id)
                ratings_db_id = publish_ratings(page_id)
                
                st.write(f"✅ Completed: {title}")
                
        except Exception as e:
            st.write(f"❌ Failed: {title} - {str(e)}")
            continue
        
        progress_bar.progress((i + 1) / len(pages))
    
    status_text.text("Pipeline completed!")
    st.success(f"Processed {len(pages)} projects")
    
    get_audit_logger(
        user=st.session_state.username,
        role=st.session_state.get("role", "N/A"),
        action="NOTION_FULL_PIPELINE_COMPLETED",
        details=f"Processed {len(pages)} projects in bulk pipeline"
    ) 