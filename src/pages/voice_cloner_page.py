import streamlit as st
import asyncio
from datetime import datetime
from typing import Optional
from src.pages.base_page import BasePage
from src.controllers.voice_cloner_controller import VoiceClonerController, VoiceClonerInput
from src.config import OPENROUTER_PRIMARY_MODEL

class VoiceClonerPage(BasePage):
    """Voice Cloner page for AI-powered voice style cloning."""
    
    def __init__(self):
        super().__init__("Voice Cloner", "🎙️ Voice Cloner")
        self.controller = VoiceClonerController()
    
    def get_current_user(self) -> str:
        """Get the current authenticated user."""
        return st.session_state.get('username', 'anonymous')
    
    def _process_pending_request(self):
        """Process a pending voice cloning request."""
        if 'voice_cloner_request' not in st.session_state:
            return
            
        request = st.session_state.voice_cloner_request
        
        # Process the request synchronously
        self._process_voice_cloning_sync(
            request['writing_example_1'],
            request['writing_example_2'], 
            request['writing_example_3'],
            request['new_piece_to_create'],
            request['selected_model']
        )
        
        # Clean up the request
        del st.session_state.voice_cloner_request
    
    async def render(self):
        """Render the voice cloner page."""
        if not self.check_authentication():
            self.show_auth_required_message()
            return
        
        self.show_page_header("🎙️ Voice Cloner", "AI-powered text reformatting to match your voice style")
        
        # Initialize session state
        if 'voice_cloner_result' not in st.session_state:
            st.session_state.voice_cloner_result = None
        if 'voice_cloner_processing' not in st.session_state:
            st.session_state.voice_cloner_processing = False
        
        # Enhanced main form with better UX
        with st.form("voice_cloner_form"):
            # Progress indicator
            progress_container = st.container()
            
            st.subheader("📝 Writing Examples")
            st.markdown("""
            **Instructions:** Provide three writing examples that represent your unique voice style. 
            These should be samples of your natural writing (emails, messages, articles, etc.).
            
            **Tips for better results:**
            - Use examples from different contexts (formal, casual, etc.)
            - Each example should be at least 20 characters long
            - Include your typical sentence structure and vocabulary
            """)
            
            # Character count tracking for examples
            example_cols = st.columns(3)
            examples_data = []
            
            for i, col in enumerate(example_cols):
                with col:
                    example_text = st.text_area(
                        f"Writing Example {i+1}",
                        height=150,
                        placeholder=f"Paste your {['first', 'second', 'third'][i]} writing example here...",
                        key=f"writing_example_{i+1}",
                        help=f"Example {i+1}: Write in your natural style. Min 20 characters."
                    )
                    
                    # Real-time character count and validation
                    char_count = len(example_text.strip()) if example_text else 0
                    if char_count > 0:
                        if char_count < 20:
                            st.error(f"⚠️ Too short ({char_count}/20 min)")
                        elif char_count > 10000:
                            st.error(f"⚠️ Too long ({char_count}/10,000 max)")
                        else:
                            st.success(f"✅ Good length ({char_count} chars)")
                    else:
                        st.info("Enter your writing example")
                    
                    examples_data.append(example_text)
            
            writing_example_1, writing_example_2, writing_example_3 = examples_data
            
            st.subheader("✍️ Text to Reformat")
            new_piece_to_create = st.text_area(
                "Paste the text you want to reformat in your voice style:",
                height=150,
                placeholder="Paste your existing text here. The AI will reformat it to match your voice style and make it sound more human-like...",
                key="new_piece_to_create",
                help="The text you want to transform using your writing style. Min 10 characters, max 50,000."
            )
            
            # Real-time validation for input text
            input_char_count = len(new_piece_to_create.strip()) if new_piece_to_create else 0
            if input_char_count > 0:
                if input_char_count < 10:
                    st.error(f"⚠️ Text too short ({input_char_count}/10 min)")
                elif input_char_count > 50000:
                    st.error(f"⚠️ Text too long ({input_char_count}/50,000 max)")
                    st.warning("💡 Consider breaking long texts into smaller sections for better results.")
                else:
                    # Estimate processing time
                    estimated_time = max(30, input_char_count / 50)  # Rough estimate
                    if input_char_count > 5000:
                        st.info(f"📊 Large text detected ({input_char_count:,} chars). Estimated processing: {estimated_time:.0f}s. Will use chunked processing.")
                    else:
                        st.success(f"✅ Good length ({input_char_count:,} chars). Estimated processing: {estimated_time:.0f}s")
            else:
                st.info("Enter the text you want to reformat")
            
            st.subheader("🤖 AI Model Selection")
            available_models = self.controller.get_available_models()
            
            # Create model selection
            model_options = list(available_models.keys())
            model_labels = [available_models[key] for key in model_options]
            
            # Find default model index
            default_index = 0
            if OPENROUTER_PRIMARY_MODEL in model_options:
                default_index = model_options.index(OPENROUTER_PRIMARY_MODEL)
            
            selected_model_label = st.selectbox(
                "Select AI Model:",
                options=model_labels,
                index=default_index,
                key="selected_model",
                help="Choose the AI model for voice cloning. Different models have varying performance characteristics and processing times."
            )
            
            # Get the actual model key from the label
            try:
                selected_model = model_options[model_labels.index(selected_model_label)]
            except ValueError:
                # Fallback to first model if there's an issue
                selected_model = model_options[0]
            
            # Accessibility and keyboard shortcuts info
            with st.expander("⌨️ Keyboard Shortcuts & Accessibility", expanded=False):
                st.markdown("""
                **Keyboard Shortcuts:**
                - `Tab` - Navigate between form fields
                - `Shift + Tab` - Navigate backwards
                - `Enter` - Submit form (when focused on submit button)
                - `Ctrl + A` (Cmd + A on Mac) - Select all text in active field
                - `Escape` - Clear focus from current field
                
                **Accessibility Features:**
                - Screen reader compatible with ARIA labels
                - High contrast mode support
                - Keyboard-only navigation
                - Clear error messages and instructions
                - Character count indicators for length validation
                """)
            
            # Submit button with enhanced accessibility
            submitted = st.form_submit_button(
                "🎯 Reformat Text",
                disabled=st.session_state.voice_cloner_processing,
                help="Press Enter to submit the form or click this button to start voice cloning",
                use_container_width=True
            )
            
            if submitted:
                # Enhanced input validation
                validation_errors = []
                
                if not all([writing_example_1, writing_example_2, writing_example_3, new_piece_to_create]):
                    validation_errors.append("Please fill in all writing examples and the text to reformat.")
                
                # Check individual field lengths
                examples = [
                    ("Writing Example 1", writing_example_1),
                    ("Writing Example 2", writing_example_2), 
                    ("Writing Example 3", writing_example_3)
                ]
                
                for name, example in examples:
                    if example and len(example.strip()) < 20:
                        validation_errors.append(f"{name} is too short (minimum 20 characters)")
                    elif example and len(example.strip()) > 10000:
                        validation_errors.append(f"{name} is too long (maximum 10,000 characters)")
                
                if new_piece_to_create:
                    text_length = len(new_piece_to_create.strip())
                    if text_length < 10:
                        validation_errors.append("Text to reformat is too short (minimum 10 characters)")
                    elif text_length > 50000:
                        validation_errors.append("Text to reformat is too long (maximum 50,000 characters)")
                
                if validation_errors:
                    for error in validation_errors:
                        st.error(f"❌ {error}")
                else:
                    # Store the request in session state and trigger processing
                    st.session_state.voice_cloner_request = {
                        'writing_example_1': writing_example_1,
                        'writing_example_2': writing_example_2,
                        'writing_example_3': writing_example_3,
                        'new_piece_to_create': new_piece_to_create,
                        'selected_model': selected_model
                    }
                    st.session_state.voice_cloner_processing = True
                    st.info("⏳ Processing started! Please have patience - this may take several minutes depending on your text length and the selected AI model.")
                    st.rerun()
        
        # Process request if one is pending
        if st.session_state.voice_cloner_processing and 'voice_cloner_request' in st.session_state:
            self._process_pending_request()
        
        # Show processing status
        if st.session_state.voice_cloner_processing:
            with st.spinner("🔄 Reformatting text... The AI is performing 50+ internal refinement iterations."):
                st.info("The AI is analyzing your writing style and reformatting your text to match your voice while making it more human-like.")
                st.warning("⏱️ This process may take 5-10 minutes depending on the model and text length. Please be patient!")
                
                # Cancel button
                if st.button("🛑 Cancel Processing"):
                    st.session_state.voice_cloner_processing = False
                    if 'voice_cloner_request' in st.session_state:
                        del st.session_state.voice_cloner_request
                    st.warning("Processing cancelled. You can try again with a different model or shorter text.")
                    st.rerun()
        
        # Show results
        if st.session_state.voice_cloner_result:
            await self._display_results()
    
    async def _process_voice_cloning(self, example1: str, example2: str, example3: str, new_piece: str, model: str):
        """Process the voice cloning request."""
        try:
            st.session_state.voice_cloner_processing = True
            st.rerun()
            
            # Create input model
            input_data = VoiceClonerInput(
                writing_example_1=example1,
                writing_example_2=example2,
                writing_example_3=example3,
                new_piece_to_create=new_piece,
                model=model,
                username=self.get_current_user(),
                session_id=st.session_state.get('session_id', 'default')
            )
            
            # Add timeout wrapper
            import asyncio
            try:
                # Set timeout to 10 minutes (600 seconds)
                result = await asyncio.wait_for(
                    self.controller.process_voice_cloning(input_data), 
                    timeout=600
                )
                
                # Store result
                st.session_state.voice_cloner_result = result
                st.session_state.voice_cloner_processing = False
                
                # Log the activity
                from src.audit_logger import get_audit_logger
                get_audit_logger(
                    user=self.get_current_user(),
                    role=st.session_state.get('role', 'N/A'),
                    action="VOICE_CLONER_REQUEST",
                    details=f"Model: {model}, Confidence: {result.confidence_score}%, Iterations: {result.iterations_completed}, Time: {result.processing_time:.1f}s"
                )
                
                st.success("✅ Text reformatting completed successfully!")
                st.rerun()
                
            except asyncio.TimeoutError:
                st.session_state.voice_cloner_processing = False
                st.error("⏱️ Request timed out after 10 minutes. Please try with a shorter text or different model.")
                st.rerun()
            
        except ValueError as ve:
            # Handle user-friendly validation errors
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ {str(ve)}")
            
            # Provide helpful suggestions based on error type
            error_msg = str(ve).lower()
            if "too short" in error_msg:
                st.info("💡 **Tip:** Try providing longer writing examples (at least 20 characters each) and text to reformat (at least 10 characters).")
            elif "too long" in error_msg:
                st.info("💡 **Tip:** Try shortening your text. Consider breaking very long texts into smaller sections.")
            elif "empty" in error_msg:
                st.info("💡 **Tip:** Make sure all writing examples and the text to reformat are filled in.")
            elif "api key" in error_msg:
                st.info("💡 **Tip:** Please contact the administrator - the AI service is not properly configured.")
            elif "rate limit" in error_msg:
                st.info("💡 **Tip:** Please wait a few minutes and try again. The AI service has temporary usage limits.")
            elif "timeout" in error_msg:
                st.info("💡 **Tip:** Try using a different AI model or shorter text. Some models may be slower than others.")
            elif "unavailable" in error_msg:
                st.info("💡 **Tip:** The AI service is temporarily down. Please try again in a few minutes.")
            
            st.rerun()
            
        except Exception as e:
            # Handle unexpected errors
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ An unexpected error occurred: {str(e)}")
            st.info("💡 **Troubleshooting:** Please try again. If the problem persists, try with a different AI model or shorter text.")
            
            # Only show debug info in development/debug mode
            if st.session_state.get('debug_mode', False):
                import traceback
                with st.expander("🔍 Technical Details (Debug Mode)"):
                    st.code(traceback.format_exc())
            
            st.rerun()
    
    def _process_voice_cloning_sync(self, example1: str, example2: str, example3: str, new_piece: str, model: str):
        """Process the voice cloning request using async wrapper for consistency."""
        try:
            # Create input model
            input_data = VoiceClonerInput(
                writing_example_1=example1,
                writing_example_2=example2,
                writing_example_3=example3,
                new_piece_to_create=new_piece,
                model=model,
                username=self.get_current_user(),
                session_id=st.session_state.get('session_id', 'default')
            )
            
            # Process using the sync wrapper that calls async method consistently
            result = self.controller.process_voice_cloning_sync(input_data)
            
            # Store result
            st.session_state.voice_cloner_result = result
            st.session_state.voice_cloner_processing = False
            
            # Log the activity
            try:
                from src.audit_logger import get_audit_logger
                get_audit_logger(
                    user=self.get_current_user(),
                    role=st.session_state.get('role', 'N/A'),
                    action="VOICE_CLONER_REQUEST",
                    details=f"Model: {model}, Confidence: {result.confidence_score}%, Iterations: {result.iterations_completed}, Time: {result.processing_time:.1f}s"
                )
            except Exception as log_error:
                # Don't fail the whole process if logging fails
                print(f"Warning: Failed to log activity: {log_error}")
            
            st.success("✅ Text reformatting completed successfully!")
            st.rerun()
            
        except ValueError as ve:
            # Handle user-friendly validation errors
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ {str(ve)}")
            
            # Provide helpful suggestions based on error type
            error_msg = str(ve).lower()
            if "too short" in error_msg:
                st.info("💡 **Tip:** Try providing longer writing examples (at least 20 characters each) and text to reformat (at least 10 characters).")
            elif "too long" in error_msg:
                st.info("💡 **Tip:** Try shortening your text. Consider breaking very long texts into smaller sections.")
            elif "empty" in error_msg:
                st.info("💡 **Tip:** Make sure all writing examples and the text to reformat are filled in.")
            elif "api key" in error_msg:
                st.info("💡 **Tip:** Please contact the administrator - the AI service is not properly configured.")
            elif "rate limit" in error_msg:
                st.info("💡 **Tip:** Please wait a few minutes and try again. The AI service has temporary usage limits.")
            elif "timeout" in error_msg:
                st.info("💡 **Tip:** Try using a different AI model or shorter text. Some models may be slower than others.")
            elif "unavailable" in error_msg:
                st.info("💡 **Tip:** The AI service is temporarily down. Please try again in a few minutes.")
            elif "event loop" in error_msg or "asyncio" in error_msg:
                st.info("💡 **Tip:** There was an async processing issue. Please try again - this is usually temporary.")
            
            st.rerun()
            
        except Exception as e:
            # Handle unexpected errors
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ An unexpected error occurred: {str(e)}")
            st.info("💡 **Troubleshooting:** Please try again. If the problem persists, try with a different AI model or shorter text.")
            
            # Only show debug info in development/debug mode
            if st.session_state.get('debug_mode', False):
                import traceback
                with st.expander("🔍 Technical Details (Debug Mode)"):
                    st.code(traceback.format_exc())
            
            st.rerun()
    
    async def _display_results(self):
        """Display the voice cloning results with enhanced UX."""
        result = st.session_state.voice_cloner_result
        
        st.subheader("🎯 Reformatted Text Result")
        
        # Enhanced responsive metrics display
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Color-coded confidence score
            confidence = result.confidence_score
            if confidence >= 80:
                st.metric("Confidence Score", f"{confidence}%", help="High confidence - excellent voice match")
                st.success("🎯 Excellent Match")
            elif confidence >= 60:
                st.metric("Confidence Score", f"{confidence}%", help="Good confidence - solid voice match")
                st.info("👍 Good Match")
            else:
                st.metric("Confidence Score", f"{confidence}%", help="Lower confidence - consider providing more diverse writing examples")
                st.warning("⚠️ Fair Match")
        
        with col2:
            st.metric("Iterations Completed", result.iterations_completed, help="Number of AI refinement cycles completed")
            if result.iterations_completed >= 50:
                st.success("🔄 Full Processing")
            else:
                st.info("⚡ Fast Processing")
        
        with col3:
            processing_time = result.processing_time
            st.metric("Processing Time", f"{processing_time:.1f}s", help="Total time taken for voice cloning")
            if processing_time < 30:
                st.success("⚡ Fast")
            elif processing_time < 120:
                st.info("⏱️ Normal")
            else:
                st.warning("🐌 Slow")
        
        # Enhanced result display with copy functionality
        st.subheader("📄 Reformatted Text")
        
        # Character count and readability info
        char_count = len(result.final_piece)
        word_count = len(result.final_piece.split())
        st.caption(f"📊 Result: {char_count:,} characters, {word_count:,} words")
        
        # Scrollable text area for better UX with long results
        st.text_area(
            "Reformatted Text (click to select all):",
            value=result.final_piece,
            height=300,
            key="result_text_area",
            help="Click in the text area and use Ctrl+A (Cmd+A on Mac) to select all text for easy copying",
            label_visibility="collapsed"
        )
        
        # Action buttons in responsive layout
        button_col1, button_col2, button_col3 = st.columns([2, 2, 1])
        
        with button_col1:
            st.download_button(
                label="📥 Download as Text File",
                data=result.final_piece,
                file_name=f"reformatted_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                help="Download the reformatted text as a .txt file",
                use_container_width=True
            )
        
        with button_col2:
            # Copy to clipboard button (using JavaScript workaround)
            if st.button("📋 Copy to Clipboard", help="Copy the reformatted text to your clipboard", use_container_width=True):
                st.info("💡 **Tip:** Click in the text area above and use Ctrl+A then Ctrl+C (Cmd+A then Cmd+C on Mac) to copy all text.")
        
        with button_col3:
            if st.button("🗑️ Clear", help="Clear results and start over", use_container_width=True):
                st.session_state.voice_cloner_result = None
                st.rerun()
        
        # Enhanced expandable sections
        with st.expander("🎨 Style Analysis & Rules", expanded=False):
            st.markdown("**Detected Style Rules:**")
            st.code(result.style_rules, language="text")
            st.caption("These are the style patterns the AI detected from your writing examples and applied to the reformatted text.")
        
        with st.expander("📊 Processing Details", expanded=False):
            st.markdown(f"""
            **Processing Summary:**
            - **Model Used:** {st.session_state.get('last_model_used', 'Unknown')}
            - **Input Length:** {st.session_state.get('last_input_length', 'Unknown')} characters
            - **Confidence Score:** {result.confidence_score}% (based on style consistency analysis)
            - **Processing Time:** {result.processing_time:.1f} seconds
            - **Refinement Iterations:** {result.iterations_completed} cycles
            - **Processing Method:** {'Chunked' if st.session_state.get('last_input_length', 0) > 5000 else 'Standard'}
            """)
        
        # Feedback section for continuous improvement
        with st.expander("💬 Rate This Result", expanded=False):
            st.markdown("**How satisfied are you with this voice cloning result?**")
            satisfaction = st.radio(
                "Satisfaction Level:",
                options=["😍 Excellent", "😊 Good", "😐 Fair", "😞 Poor"],
                key="result_satisfaction",
                help="Your feedback helps improve the voice cloning algorithm"
            )
            
            feedback_text = st.text_area(
                "Additional Comments (optional):",
                placeholder="Share what worked well or what could be improved...",
                key="result_feedback",
                help="Optional feedback to help us improve the voice cloning experience"
            )
            
            if st.button("📤 Submit Feedback"):
                # In a real implementation, this would send feedback to analytics
                st.success("✅ Thank you for your feedback! This helps us improve the voice cloning system.")