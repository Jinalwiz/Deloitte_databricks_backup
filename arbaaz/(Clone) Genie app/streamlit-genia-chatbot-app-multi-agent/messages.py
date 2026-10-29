"""
Message classes for the chatbot application.

This module contains the message classes used throughout the app.
By keeping them in a separate module, they remain stable across
Streamlit app reruns, avoiding isinstance comparison issues.
"""
import streamlit as st
import time
from abc import ABC, abstractmethod
import matplotlib.pyplot as plt
from model_serving_utils import (
    endpoint_supports_feedback, 
    query_endpoint, 
    query_endpoint_stream, 
    _get_endpoint_task_type )
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole


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
    def __init__(self, messages, request_id):
        super().__init__()
        self.messages = messages
        # Request ID tracked to enable submitting feedback on assistant responses via the feedback endpoint
        self.request_id = request_id

    def to_input_messages(self):
        return self.messages

    def render(self, idx):
        with st.chat_message("assistant"):
            for msg in self.messages:
                #st.markdown('Calling Assist func')
                render_message_assist(msg)

            if self.request_id is not None:
                render_assistant_message_feedback(idx, self.request_id)

def render_message_assist(msg, chart_enabled='', prompt=''):
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
            elif len(msg["content"]) < 400:
                st.markdown(msg["content"].replace("tool tip","").replace("tool call",""))
            else:
                #st.write_stream(stream_data(msg["content"]))
                st.markdown(msg["content"].replace("tool tip","").replace("tool call",""))  
                if chart_enabled == 'X':
                    prepare_chart(msg["content"].replace("tool tip","").replace("tool call",""), prompt) 

def stream_data(content1):
    for word in content1.split(" "):
        yield word + " "
        time.sleep(0.025)

def prepare_chart(content, prompt):    

    endpoint = 'databricks-gpt-5'
    ENDPOINT_SUPPORTS_FEEDBACK = endpoint_supports_feedback(endpoint)
    
    content_prompt = f"User Prompt: {prompt}, Response results: {content}"
    #st.markdown(content_prompt)
    messages, request_id = query_endpoint(
                endpoint_name=endpoint,
                messages=[{"role": "system", "content": "Your task is to generate simple Python Code Script for the content provided by the User to display the data in content as single chart or multiple charts. The response should only include simple executable code script of python provided as a string or code object, no comments and no newline characters. Do not add the code to display count in the chart."},
                          {"role": "user", "content": content_prompt}],
                return_traces=ENDPOINT_SUPPORTS_FEEDBACK
            )
    #st.markdown(messages)
    try:
        plot_area = st.empty()
        #fig, ax = plt.subplots()
        #exec(messages[0]["content"])
        #st.set_page_config(page_title="Monthly Sales Dashboard", layout="wide")
        #plot_area.pyplot(exec(messages[0]["content"]))

        #plt.close('all')
        #local_env = {}
        #exec(messages[0]['content'], {}, local_env)
        #fig = plt.gcf()
        #st.pyplot(fig)
        #*******************************************
        #plt.close('all')
        #figures = []

        # Patch plt.show to collect the current figure
        #def custom_show(*args, **kwargs):
        #    fig = plt.gcf()
        #    if fig not in figures:
        #        figures.append(fig)
        #plt.show = custom_show

        #local_env = {}
        #exec(messages[0]['content'], {}, local_env)
        # Also collect any figures not explicitly shown
        #for num in plt.get_fignums():
        #    fig = plt.figure(num)
        #    if fig not in figures:
        #        figures.append(fig)

        # Display all captured figures
        #for fig in figures:
        #    st.pyplot(fig)

        # Optionally, clear figure after showing (in case you'll run more code later)
        #plt.close(fig)
        #*******************************************
        plt.close("all")
        mpl_figures = []

        def custom_show(*args, **kwargs):
            fig = plt.gcf()
            if fig not in mpl_figures:
                mpl_figures.append(fig)
        plt.show = custom_show

        local_env = {}
        exec(messages[0]['content'], {}, local_env)

        # Matplotlib render
        for num in plt.get_fignums():
            fig = plt.figure(num)
            if fig not in mpl_figures:
                mpl_figures.append(fig)
        for fig in mpl_figures:
            st.pyplot(fig)

        # Plotly render (scan locals)
        for _, v in local_env.items():
            if v is not None and v.__class__.__module__.startswith("plotly"):
                # Most Plotly figures are "BaseFigure" subclasses; this is a practical check
                if hasattr(v, "to_plotly_json"):
                    st.plotly_chart(v, use_container_width=True)
        
    except Exception as e:
        pass
        #st.markdown(str(e))
    return messages


def render_message(msg, chart_enabled='', prompt=''):
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
                st.markdown(msg["content"].replace("tool tip","").replace("tool call",""))
            else:
                #st.write_stream(stream_data(msg["content"]))
                st.markdown(msg["content"].replace("tool tip","").replace("tool call",""))
                if chart_enabled == 'X':
                    prepare_chart(msg["content"].replace("tool tip","").replace("tool call",""), prompt)  

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