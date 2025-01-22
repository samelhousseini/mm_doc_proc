# main.py

import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import uvicorn

from chainlit.utils import mount_chainlit
from chainlit.context import init_http_context
import chainlit as cl



from ai_agent_manager import AIAgentManager, AgentConfiguration

app = FastAPI()

# Global dictionaries for demonstration:
USER_TO_MANAGER = {}
USER_TO_THREAD = {}

# Example config for the Agent
GLOBAL_CONFIG = AgentConfiguration(
    name="4o-bot",
    model="gpt-4o",
    instructions="You are a helpful assistant.",
    enable_code_interpreter=True,
    enable_bing=True,
    enable_azure_search=False,
    enable_file_search=False,
    temperature=0.3,
    top_p=0.95
)

PROJECT_CONNECTION_STRING = os.getenv("FOUNDRY_PROJECT", "")


class ChatRequest(BaseModel):
    user_id: str
    message: str
    new_chat: bool = False
    stream: bool = False

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    """
    This endpoint handles chatting with the user's assigned agent.
    - If user doesn't have a manager yet, create one.
    - If new_chat = True, create a new thread for them.
    - Else, use their existing thread_id if it exists.
    - Then call manager.chat_in_thread().
    """
    user_id = req.user_id
    message = req.message

    # Ensure we have a manager for this user
    manager = USER_TO_MANAGER.get(user_id)
    if not manager:
        # create a new manager
        manager = AIAgentManager(
            connection_string=PROJECT_CONNECTION_STRING,
            config=GLOBAL_CONFIG
        )
        USER_TO_MANAGER[user_id] = manager

    # Decide which thread to use
    if req.new_chat:
        # user wants a brand new conversation
        thread_id = None  # let manager create a new thread
    else:
        # continue existing conversation if possible
        thread_id = USER_TO_THREAD.get(user_id)

    # Perform the chat
    response = manager.chat_in_thread(
        user_message=message,
        thread_id=thread_id,
        stream=req.stream
    )

    # Store the newly used thread_id for next time
    USER_TO_THREAD[user_id] = response.thread_id

    return response.dict()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
