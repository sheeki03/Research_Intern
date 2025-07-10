import streamlit as st
import asyncio
from typing import Optional
from src.pages.base_page import BasePage
from src.controllers.voice_cloner_controller import VoiceClonerController
from src.models.voice_cloner_models import VoiceClonerInput
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
        
        # Main form
        with st.form("voice_cloner_form"):
            st.subheader("📝 Writing Examples")
            st.write("Provide three writing examples that represent your voice style:")
            
            # Writing examples
            col1, col2, col3 = st.columns(3)
            
            with col1:
                writing_example_1 = st.text_area(
                    "Writing Example 1",
                    height=150,
                    placeholder="Paste your first writing example here...",
                    key="writing_example_1"
                )
            
            with col2:
                writing_example_2 = st.text_area(
                    "Writing Example 2", 
                    height=150,
                    placeholder="Paste your second writing example here...",
                    key="writing_example_2"
                )
            
            with col3:
                writing_example_3 = st.text_area(
                    "Writing Example 3",
                    height=150,
                    placeholder="Paste your third writing example here...",
                    key="writing_example_3"
                )
            
            st.subheader("✍️ Text to Reformat")
            new_piece_to_create = st.text_area(
                "Paste the text you want to reformat in your voice style:",
                height=150,
                placeholder="Paste your existing text here. The AI will reformat it to match your voice style and make it sound more human-like...",
                key="new_piece_to_create"
            )
            
            st.subheader("🤖 AI Model Selection")
            available_models = self.controller.get_available_models()
            
            # Create model selection dropdown
            model_options = list(available_models.keys())
            model_labels = [f"{available_models[key]}" for key in model_options]
            
            # Find default model index
            default_index = 0
            if OPENROUTER_PRIMARY_MODEL in model_options:
                default_index = model_options.index(OPENROUTER_PRIMARY_MODEL)
            
            selected_model_label = st.selectbox(
                "Select AI Model:",
                options=model_labels,
                index=default_index,
                key="selected_model"
            )
            
            # Get the actual model key from the label
            try:
                selected_model = model_options[model_labels.index(selected_model_label)]
            except ValueError:
                # Fallback to first model if there's an issue
                selected_model = model_options[0]
            
            # Submit button
            submitted = st.form_submit_button(
                "🎯 Reformat Text",
                disabled=st.session_state.voice_cloner_processing
            )
            
            if submitted:
                if not all([writing_example_1, writing_example_2, writing_example_3, new_piece_to_create]):
                    st.error("Please fill in all writing examples and paste the text to reformat.")
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
            
        except Exception as e:
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ Error processing voice cloning: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
            st.rerun()
    
    def _process_voice_cloning_sync(self, example1: str, example2: str, example3: str, new_piece: str, model: str):
        """Process the voice cloning request synchronously."""
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
            
            # Process synchronously
            result = self.controller.process_voice_cloning_sync(input_data)
            
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
            
        except Exception as e:
            st.session_state.voice_cloner_processing = False
            st.error(f"❌ Error processing voice cloning: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
            st.rerun()
    
    async def _display_results(self):
        """Display the voice cloning results."""
        result = st.session_state.voice_cloner_result
        
        st.subheader("🎯 Reformatted Text Result")
        
        # Show metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Confidence Score", f"{result.confidence_score}%")
        
        with col2:
            st.metric("Iterations Completed", result.iterations_completed)
        
        with col3:
            st.metric("Processing Time", f"{result.processing_time:.1f}s")
        
        # Show the final piece
        st.subheader("📄 Reformatted Text")
        st.markdown("---")
        st.markdown(result.final_piece)
        st.markdown("---")
        
        # Show style rules in expandable section
        with st.expander("🎨 Style Rules (Debug Info)"):
            st.code(result.style_rules, language="text")
        
        # Download button
        st.download_button(
            label="📥 Download Reformatted Text",
            data=result.final_piece,
            file_name="reformatted_text.txt",
            mime="text/plain"
        )
        
        # Clear result button
        if st.button("🗑️ Clear Results"):
            st.session_state.voice_cloner_result = None
            st.rerun()