from pathlib import Path
from typing import Optional, List, Any, Union, Dict, Callable, Set

from pydantic import BaseModel

# ------------------------------------------------------------------
# 1. Agent configuration model
# ------------------------------------------------------------------

class AgentConfiguration(BaseModel):
    """
    Specifies how we want to set up our Agent.
    - name: Unique name for the agent (used to see if agent is already on Azure).
    - model: The deployed model name you want to use, e.g. "gpt-4" or "gpt-35-turbo".
    - instructions: High-level system instructions for your agent's personality.
    - enable_bing: Whether to add Bing grounding tool.
    - enable_azure_search: Whether to add Azure AI Search tool.
    - enable_code_interpreter: Whether to add code interpreter tool.
    - enable_file_search: Whether to add file search tool.
    - vector_store_ids: If file search is used, list of vector store IDs. 
    - top_p, temperature, etc.: Additional parameters for the chat model if desired.
    """
    name: str = "multimodal-doc-proc-assistant"
    model: str = "gpt-4o"
    instructions: str = "You are a helpful assistant, that assists with searching multimodal documents."
    
    enable_bing: bool = True
    bing_connection_name: Optional[str] = "bing-grounding"
    
    enable_azure_search: bool = False
    azure_search_connection_name: Optional[str] = None
    azure_search_index_name: Optional[str] = None
    
    enable_code_interpreter: bool = True
    
    enable_file_search: bool = False
    vector_store_ids: Optional[List[str]] = None  # If file_search is used, provide vector store IDs

    # Additional advanced params
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    enable_tracing: bool = False
    user_functions: Set[Callable[..., Any]] = set()


# ------------------------------------------------------------------
# 2. Data models for chat returns
# ------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRunStep(BaseModel):
    step_type: str
    status: str


class ChatResponse(BaseModel):
    """
    Enhanced return object from the chat() method,
    bundling conversation messages, run steps, file references,
    plus metadata like agent_id, thread_id, and run_id.
    """
    agent_id: str
    thread_id: str
    run_id: Optional[str]  # Might be None if no run was created
    status: str

    answer: str
    messages: List[ChatMessage]
    run_steps: List[ChatRunStep]
    file_ids: List[str] = []
    downloaded_files: List[str] = []
    tool_outputs: List[str] = []