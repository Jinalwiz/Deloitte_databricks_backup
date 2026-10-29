import logging
import os
import streamlit as st
#import mlflow
#print('Tracking URI', mlflow.get_tracking_uri())

from model_serving_utils import (
    endpoint_supports_feedback, 
    query_endpoint, 
    query_endpoint_stream, 
    _get_endpoint_task_type,
)
from collections import OrderedDict
from messages import UserMessage, AssistantResponse, render_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#### Code for the Genie app
import functools
import os
from typing import Any, Generator, Literal, Optional
import json
import pandas as pd

import mlflow
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    ChatDatabricks,
    UCFunctionToolkit,
    DatabricksFunctionClient,
    set_uc_function_client
)
client = DatabricksFunctionClient()
set_uc_function_client(client) 
from databricks_langchain.genie import GenieAgent
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from mlflow.langchain.chat_agent_langgraph import ChatAgentState
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)
from pydantic import BaseModel


# --- Init state ---
if "history" not in st.session_state:
    st.session_state.history = []




###################################################
## Create a GenieAgent with access to a Genie Space
###################################################

# TODO add GENIE_SPACE_ID and a description for this space
# You can find the ID in the URL of the genie room /genie/rooms/<GENIE_SPACE_ID>
# Example description: This Genie agent can answer questions based on a database containing tables related to enterprise software sales, including accounts, opportunities, opportunity history, fiscal periods, quotas, targets, teams, and users. Use Genie to fetch and analyze data from these tables by specifying the relevant columns and filters. Genie can execute SQL queries to provide precise data insights based on your questions.
#GENIE_SPACE_ID = "01f089d9fb471742a42a3de8dd3467c5"
#genie_agent_description = "This Genie agent can answer questions based on a database containing tables related to SAP provided Fiori apps list containing detailed information about applications within the SAP S/4HANA FIORI ecosystem, including descriptions, statuses, components, catalogs, groups, roles, and various technical details. And list of CDS Views table provides information related to application components and their corresponding CDS (Core Data Services) views, including view names, descriptions, data categories, and development states."

GENIE_SPACE_ID = "01f088c73c77126dba90f2775171c1bd"
genie_agent_description = "This Genie agent contains detailed information about billing transactions, including unique identifiers for billing documents and items, billing dates, sales item categories, materials involved, and the total net amount for each transaction. It is useful for tracking sales performance, analyzing inventory, and financial reporting."

genie_agent = GenieAgent(
    genie_space_id=GENIE_SPACE_ID,
    genie_agent_name="Fiori App Assistant Genie",
    description=genie_agent_description,
    client=WorkspaceClient(
        host=os.getenv("DB_MODEL_SERVING_HOST_URL"),
        token=os.getenv("DATABRICKS_GENIE_PAT"),
    ),
)


############################################
# Define your LLM endpoint and system prompt
############################################

# TODO: Replace with your model serving endpoint
# multi-agent Genie works best with claude 3.7 or gpt 4o models.
LLM_ENDPOINT_NAME = "databricks-claude-3-7-sonnet"
#LLM_ENDPOINT_NAME = "databricks-llama-4-maverick"
llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)


############################################################
# Create a code agent
# You can also create agents with access to additional tools
############################################################
tools = []

# TODO if desired, add additional tools and update the description of this agent
uc_tool_names = ["system.ai.*"]
uc_toolkit = UCFunctionToolkit(function_names=uc_tool_names)
tools.extend(uc_toolkit.tools)
code_agent_description = (
    "The Coder agent specializes in solving programming challenges, generating code snippets, debugging issues, and explaining complex coding concepts.",
)
code_agent = create_react_agent(llm, tools=tools)

#############################
# Define the supervisor agent
#############################

# TODO update the max number of iterations between supervisor and worker nodes
# before returning to the user
MAX_ITERATIONS = 3

worker_descriptions = {
    "Genie": genie_agent_description
    #"Coder": code_agent_description,
}

formatted_descriptions = "\n".join(
    f"- {name}: {desc}" for name, desc in worker_descriptions.items()
)

system_prompt = f"Decide between routing between the following workers or ending the conversation if an answer is provided. \n{formatted_descriptions}"
options = ["FINISH"] + list(worker_descriptions.keys())
FINISH = {"next_node": "FINISH"}

def supervisor_agent(state):
    count = state.get("iteration_count", 0) + 1
    if count > MAX_ITERATIONS:
        return FINISH
    
    class nextNode(BaseModel):
        next_node: Literal[tuple(options)]

    preprocessor = RunnableLambda(
        lambda state: [{"role": "system", "content": system_prompt}] + state["messages"]
    )
    supervisor_chain = preprocessor | llm.with_structured_output(nextNode)
    next_node = supervisor_chain.invoke(state).next_node
    
    # if routed back to the same node, exit the loop
    if state.get("next_node") == next_node:
        return FINISH
    return {
        "iteration_count": count,
        "next_node": next_node
    }

#######################################
# Define our multiagent graph structure
#######################################


def agent_node(state, agent, name):
    result = agent.invoke(state)
    return {
        "messages": [
            {
                "role": "assistant",
                "content": result["messages"][-1].content,
                "name": name,
            }
        ]
    }


def final_answer(state):
    #prompt = "Using only the content in the messages, respond to the previous user question using the answer given by the other assistant #messages."
    prompt = '''You are the Supervisor Agent.    
            - Your job is to transform the response you will receive from the agent to a more detailed natural-language summary.
            - If you get a tabular response then provide the detailed summary of the tabular response received as your response 
            - If you get a tabular response then do not mention the number of entries in the table in output or table word in the output
            - If you get a tabular response then Interpret what the columns and rows represent.  
            - If you get a tabular response then Summarize clearly without repeating the raw table.  
            - Cover all key data points (no omissions).  
            - Describe each row.    
            - Use clear structure (bullets, sections, or short paragraphs).   
            
            Final output = a well-structured, human-readable summary of the tabular response or a detailed summary if you receive the respone in any other format.'''
    prompt = '''You are the Supervisor Agent.    
            - Your job is to transform the response you will receive from the agent to a more detailed natural-language summary.  
            - Cover all key data points (no omissions).     
            - Use clear structure (bullets, sections, or short paragraphs).   
            
            Final output = a well-structured, human-readable summary of the response you recieved from the agent and present it as your own response.'''

    preprocessor = RunnableLambda(
        lambda state: state["messages"] + [{"role": "user", "content": prompt}]
    )
    final_answer_chain = preprocessor | llm
    return {"messages": [final_answer_chain.invoke(state)]}


class AgentState(ChatAgentState):
    next_node: str
    iteration_count: int


code_node = functools.partial(agent_node, agent=code_agent, name="Coder")
genie_node = functools.partial(agent_node, agent=genie_agent, name="Genie")

workflow = StateGraph(AgentState)
workflow.add_node("Genie", genie_node)
#workflow.add_node("Coder", code_node)
workflow.add_node("supervisor", supervisor_agent)
workflow.add_node("final_answer", final_answer)

workflow.set_entry_point("supervisor")
# We want our workers to ALWAYS "report back" to the supervisor when done
for worker in worker_descriptions.keys():
    workflow.add_edge(worker, "supervisor")

# Let the supervisor decide which next node to go
workflow.add_conditional_edges(
    "supervisor",
    lambda x: x["next_node"],
    {**{k: k for k in worker_descriptions.keys()}, "FINISH": "final_answer"},
)
workflow.add_edge("final_answer", END)
multi_agent = workflow.compile()

###################################
# Wrap our multi-agent in ChatAgent
###################################


class LangGraphChatAgent(ChatAgent):
    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        request = {
            "messages": [m.model_dump_compat(exclude_none=True) for m in messages]
        }

        messages = []
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                messages.extend(
                    ChatAgentMessage(**msg) for msg in node_data.get("messages", [])
                )
        return ChatAgentResponse(messages=messages)

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> Generator[ChatAgentChunk, None, None]:
        request = {
            "messages": [m.model_dump_compat(exclude_none=True) for m in messages]
        }
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                yield from (
                    ChatAgentChunk(**{"delta": msg})
                    for msg in node_data.get("messages", [])
                )


# Create the agent object, and specify it as the agent object to use when
# loading the agent back for inference via mlflow.models.set_model()
mlflow.langchain.autolog()
AGENT = LangGraphChatAgent(multi_agent)
mlflow.models.set_model(AGENT)

st.title("Sales and Billing Assistant")
st.write(f"Find invoice, sales, and billing info from S/4HANA — just let me know what you need!")
st.logo(image = 'https://upload.wikimedia.org/wikipedia/commons/8/8f/SAP-Logo.svg', size="large")

####
#st.markdown(os.getenv("DATABRICKS_CLIENT_SECRET"))

# --- Render chat history ---
for i, element in enumerate(st.session_state.history):
    element.render(i)
    #st.markdown(element)

# Regenerate button
#if st.session_state.history: # Only show button if there are messages

# --- Chat input (must run BEFORE rendering messages) ---
prompt = st.chat_input("Ask a question", key ="chat_input")

#if st.button("Regenerate Response"):
#    prompt = prompt
if prompt:
    
    user_msg = UserMessage(content=prompt)
    st.session_state.history.append(user_msg)
    user_msg.render(len(st.session_state.history) - 1)

    # Convert history to standard chat message format for the query methods
    #input_messages = [msg for elem in st.session_state.history for msg in elem.to_input_messages()]

    output = AGENT.predict({"messages": [{"role": "user", "content": prompt}]})
    with st.chat_message("assistant"):
        #st.markdown(list(list(output)[0][1][-1])[1][1].split('JSON_OUTPUT')[0].replace("#", "###").replace("$", "\$"))
        st.markdown(list(list(output)[0][1][-1])[1][1].replace("#", "###").replace("$", "\$"))
        #if 'JSON_OUTPUT' in list(list(output)[0][1][-1])[1][1]:
        #    start_index = list(list(output)[0][1][-1])[1][1].find('[') - 1
        #    end_index = list(list(output)[0][1][-1])[1][1].find(']') + 1
        #    json_data = list(list(output)[0][1][-1])[1][1][start_index:end_index]
        #    if json_data:
        #        st.markdown(json_data)
        #        data = json.loads(json_data)
        #        df = pd.DataFrame(data)

        #    st.bar_chart(df, x=list(data[0].keys())[0], y=list(data[0].keys())[1], x_label=list(data[0].keys())[0], y_label=list(data[0].keys())[1])


    #assistant_response = AssistantResponse(list(list(output)[0][1][-1])[1][1].split('JSON_OUTPUT')[0].replace("#", "###").replace("$", "\$"))
    assistant_response = AssistantResponse(list(list(output)[0][1][-1])[1][1].replace("#", "###").replace("$", "\$"))
    # Add assistant response to history
    #st.session_state.history.append(list(list(output)[0][1][-1])[1][1].replace("#", "###"))
    st.session_state.history.append(assistant_response)


