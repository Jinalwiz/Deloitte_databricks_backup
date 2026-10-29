"""
Message classes for the chatbot application.

This module contains the message classes used throughout the app.
By keeping them in a separate module, they remain stable across
Streamlit app reruns, avoiding isinstance comparison issues.
"""
import streamlit as st
import time
from abc import ABC, abstractmethod


class Message(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def to_input_messages(self):
        """Convert this message into a list of dicts suitable for the model API."""
        pass

    @abstractmethod
    def render(self, idx):
        """Render the message in the Streamlit app."""
        pass


class UserMessage(Message):
    def __init__(self, content):
        super().__init__()
        self.content = content

    def to_input_messages(self):
        return [{
            "role": "user",
            "content": self.content
        }]

    def render(self, _):
        with st.chat_message("user"):
            st.markdown(self.content)
            


class AssistantResponse(Message):
    #def __init__(self, messages, request_id):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages
        # Request ID tracked to enable submitting feedback on assistant responses via the feedback endpoint
        #self.request_id = request_id

    def to_input_messages(self):
        return self.messages

    def render(self, idx):
        with st.chat_message("assistant"):
            #for msg in self.messages:
                #st.markdown('Calling Assist func')
                #render_message_assist(msg)
            st.markdown(self.messages)

            #if self.request_id is not None:
            #    render_assistant_message_feedback(idx, self.request_id)

def render_message_assist(msg):
    """Render a single message."""
    #st.markdown("Inside Assist Message")
    if msg["role"] == "assistant":
        # Render content first if it exists
        if msg["content"]:
            if "</think>" in msg["content"]:
                pass
            elif "<think>" in msg["content"]:
                pass
            elif "</name>" in msg["content"]:
                pass
            elif msg["content"][0] == "|":
                pass
            elif len(msg["content"]) < 250:
                st.markdown(msg["content"])
            else:
                #st.write_stream(stream_data(msg["content"]))
                st.markdown(msg["content"])  

def stream_data(content1):
    for word in content1.split(" "):
        yield word + " "
        time.sleep(0.025)

def render_message(msg):
    """Render a single message."""
    #st.markdown("Inside Render Message")
    if msg["role"] == "assistant":
        # Render content first if it exists
        #st.markdown(msg)
        if msg["content"]:
            if "</think>" in msg["content"]:
                pass
            elif "<think>" in msg["content"]:
                pass
            elif "</name>" in msg["content"]:
                pass
            elif msg["content"][0] == "|":
                pass
            elif len(msg["content"]) < 400:
                st.markdown(msg["content"])
            else:
                st.write_stream(stream_data(msg["content"]))
                #st.markdown(msg["content"])  

    '''    
        # Then render tool calls if they exist
        if "tool_calls" in msg and msg["tool_calls"]:
            for call in msg["tool_calls"]:
                fn_name = call["function"]["name"]
                args = call["function"]["arguments"]
                st.markdown(f"🛠️ Calling **`{fn_name}`** with:\n```json\n{args}\n```")
    elif msg["role"] == "tool":
        st.markdown("🧰 Tool Response:")
        st.code(msg["content"], language="json")
    '''

@st.fragment
def render_assistant_message_feedback(i, request_id):
    """Render feedback UI for assistant messages."""
    from model_serving_utils import submit_feedback
    import os
    
    def save_feedback(index):
        serving_endpoint = os.getenv('SERVING_ENDPOINT')
        if serving_endpoint:
            submit_feedback(
                endpoint=serving_endpoint,
                request_id=request_id,
                rating=st.session_state[f"feedback_{index}"]
            )
    
    st.feedback("thumbs", key=f"feedback_{i}", on_change=save_feedback, args=[i])