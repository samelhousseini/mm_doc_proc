import os
import time
from pathlib import Path

import asyncio

from typing import Optional, List, Union, Any
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import Evaluation, Dataset, EvaluatorConfiguration, ConnectionType
from azure.identity import DefaultAzureCredential
from azure.ai.projects.models import (
    CodeInterpreterTool,
    MessageAttachment, 
    RunStatus,
    FileSearchTool,
    FilePurpose,
    AgentEventHandler,
    BingGroundingTool,
    AzureAISearchTool,
    FunctionTool,
    MessageDeltaTextContent,
    MessageTextContent
)
from azure.ai.projects.models import ToolSet, FunctionTool

class MyEventHandler(AgentEventHandler):
    """Optional: A sample event handler for streaming."""
    def on_message_delta(self, delta):
        for content_part in delta.delta.content:
            if isinstance(content_part, MessageDeltaTextContent):
                text_value = content_part.text.value if content_part.text else "No text"
                print(f"[Stream delta] {text_value}")

    def on_thread_message(self, message):
        print(f"[Event] ThreadMessage created. ID: {message.id}, Status: {message.status}")

    def on_thread_run(self, run):
        print(f"[Event] ThreadRun status: {run.status}")

    def on_run_step(self, step):
        print(f"[Event] RunStep type: {step.type}, Status: {step.status}")

    def on_error(self, data: str) -> None:
        print(f"[Event] Error occurred: {data}")

    def on_done(self) -> None:
        print("[Event] Stream completed.")

    def on_unhandled_event(self, event_type: str, event_data: Any):
        print(f"[Event] Unhandled event: {event_type}, Data: {event_data}")


class AIAgentWrapper:
    def __init__(self, connection_string: str):
        """Initialize the AIProjectClient and prepare for Agent operations."""
        self.client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(),
            conn_str=connection_string,
        )

    def create_agent(self, 
                     model: str,
                     instructions: str,
                     toolset: Optional[ToolSet] = None,
                     tools: Optional[List[dict]] = None,
                     tool_resources: Optional[List[dict]] = None,
                     headers: Optional[dict] = None):
        """Create an Agent with given model, instructions, and optional tools."""
        agent = self.client.agents.create_agent(
            model=model,
            name="my-assistant",
            instructions=instructions,
            toolset=toolset,
            tools=tools,
            tool_resources=tool_resources,
            headers=headers
        )

        print(f"Created agent, ID: {agent.id}")

        return agent

    def create_thread(self, tool_resources: Optional[List[dict]] = None):
        """Create a thread for a conversation."""
        thread = self.client.agents.create_thread(tool_resources=tool_resources)
        return thread

    def create_message(self, thread_id: str, role: str, content: str, attachments: Optional[List[MessageAttachment]] = None):
        """Create a user or system message in the thread."""
        message = self.client.agents.create_message(
            thread_id=thread_id,
            role=role,
            content=content,
            attachments=attachments
        )
        return message

    def upload_file(self, file_path: str, purpose: FilePurpose = FilePurpose.AGENTS):
        """Upload a file for Agents."""
        file_info = self.client.agents.upload_file_and_poll(file_path=file_path, purpose=purpose)
        return file_info

    def create_vector_store(self, file_ids: List[str], name: str):
        """Create a vector store for file search."""
        vector_store = self.client.agents.create_vector_store_and_poll(file_ids=file_ids, name=name)
        return vector_store

    def create_run(self, thread_id: str, assistant_id: str):
        """Create a run and poll until completion (no function tools)."""
        run = self.client.agents.create_run(thread_id=thread_id, assistant_id=assistant_id)
        # Poll until the run is completed or failed.
        while run.status in [RunStatus.QUEUED, RunStatus.IN_PROGRESS, RunStatus.REQUIRES_ACTION]:
            time.sleep(1)
            run = self.client.agents.get_run(thread_id=thread_id, run_id=run.id)
        return run

    def create_and_process_run(self, thread_id: str, assistant_id: str):
        """Create and process run (if function tools are used, they will be automatically invoked)."""
        run = self.client.agents.create_and_process_run(thread_id=thread_id, assistant_id=assistant_id)
        return run

    def stream_run(self, thread_id: str, assistant_id: str, event_handler: Optional[AgentEventHandler] = None):
        """Create a streaming run for real-time token-by-token output."""
        if event_handler is None:
            event_handler = MyEventHandler()

        with self.client.agents.create_stream(thread_id=thread_id, assistant_id=assistant_id, event_handler=event_handler) as stream:
            stream.until_done()

    def list_messages(self, thread_id: str):
        """List messages from the agent."""
        messages = self.client.agents.list_messages(thread_id=thread_id)
        # Print messages' last text content:
        for data_point in reversed(messages.data):
            last_message_content = data_point.content[-1]
            if isinstance(last_message_content, MessageTextContent):
                print(f"{data_point.role}: {last_message_content.text.value}")
        return messages

    def get_messages(self, thread_id: str):
        """Get richer message objects, helpful if tools are used."""
        return self.client.agents.get_messages(thread_id=thread_id)

    def save_file(self, file_id: str, target_name: str):
        """Save agent-generated file to local drive."""
        self.client.agents.save_file(file_id=file_id, file_name=target_name)

    def get_file_content(self, file_id: str, file_name: str, target_dir: Optional[Union[str, Path]] = None):
        """Retrieve file content asynchronously and save it to local disk."""
        # Because get_file_content is async, we use asyncio.run here
        async def _get_file_content():
            path = Path(target_dir).expanduser().resolve() if target_dir else Path.cwd()
            path.mkdir(parents=True, exist_ok=True)

            file_content_stream = await self.client.agents.get_file_content(file_id)
            if not file_content_stream:
                raise RuntimeError(f"No content retrievable for file ID '{file_id}'.")

            chunks = []
            async for chunk in file_content_stream:
                if isinstance(chunk, (bytes, bytearray)):
                    chunks.append(chunk)
                else:
                    raise TypeError(f"Expected bytes or bytearray, got {type(chunk).__name__}")

            target_file_path = path / file_name
            with open(target_file_path, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)

            return target_file_path

        return asyncio.run(_get_file_content())

    def delete_agent(self, agent_id: str):
        """Cleanup: Delete agent."""
        self.client.agents.delete_agent(agent_id)

    def delete_all_agents(self):
        """Cleanup: Delete ALL agents."""
        agents = self.client.agents.list_agents()
        for id in [x['id'] for x in agents.items().mapping['data']]:
            self.delete_agent(id)

    def delete_all_files(self):
        """Cleanup: Delete ALL files."""
        files = self.client.agents.list_files()
        for id in [x['id'] for x in files.items().mapping['data']]:
            self.delete_file(id)

    def delete_all_vector_stores(self):
        """Cleanup: Delete ALL vector stores."""
        vector_stores = self.client.agents.list_vector_stores()
        for id in [x['id'] for x in vector_stores.items().mapping['data']]:
            self.delete_vector_store(id)
             
    def delete_file(self, file_id: str):
        """Cleanup: Delete file."""
        self.client.agents.delete_file(file_id=file_id)

    def delete_vector_store(self, vector_store_id: str):
        """Cleanup: Delete vector store."""
        self.client.agents.delete_vector_store(vector_store_id)

    def create_file_search_agent(self, model: str, instructions: str, file_ids: List[str]):
        """Create an agent with File Search tool."""
        file_search_tool = FileSearchTool(vector_store_ids=file_ids)
        agent = self.create_agent(model=model, instructions=instructions,
                                  tools=file_search_tool.definitions,
                                  tool_resources=file_search_tool.resources)
        return agent

    def create_code_interpreter_agent(self, model: str, instructions: str, file_ids: Optional[List[str]] = None):
        """Create an agent with Code Interpreter tool."""
        if file_ids:
            code_tool = CodeInterpreterTool(file_ids=file_ids)
            agent = self.create_agent(model=model, instructions=instructions,
                                      tools=code_tool.definitions,
                                      tool_resources=code_tool.resources)
        else:
            code_tool = CodeInterpreterTool()
            agent = self.create_agent(model=model, instructions=instructions,
                                      tools=code_tool.definitions)
        return agent

    def create_bing_grounding_agent(self, model: str, instructions: str, bing_connection_name: str):
        """Create an agent with Bing grounding."""
        # Requires a Bing connection already set up in your project
        bing_connection = self.client.connections.get(connection_name=bing_connection_name)
        bing = BingGroundingTool(connection_id=bing_connection.id)
        # Bing grounding may require a preview header
        agent = self.create_agent(model=model, instructions=instructions,
                                  tools=bing.definitions,
                                  headers={"x-ms-enable-preview": "true"})
        return agent

    def create_azure_ai_search_agent(self, model: str, instructions: str, index_name: str, connection_name: Optional[str] = None):
        """Create an agent with Azure AI Search tool."""

        if connection_name is None:
            # Find a CognitiveSearch connection
            conn_list = self.client.connections.list()
            conn_id = None
            for conn in conn_list:
                if conn.connection_type == "CognitiveSearch":
                    conn_id = conn.id
                    break
            if not conn_id:
                raise RuntimeError("No CognitiveSearch connection found.")
        else:
            conn = self.client.connections.get(connection_name=connection_name)
            conn_id = conn.id
            if not conn_id:
                raise RuntimeError("No CognitiveSearch connection found.")
            
        print("Found connection:", conn_id)

        ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name=index_name)

        print("Connection properties:", ai_search.definitions, ai_search.resources)

        agent = self.create_agent(model=model, instructions=instructions,
                                  tools=ai_search.definitions,
                                  tool_resources=ai_search.resources,
                                  headers={"x-ms-enable-preview": "true"})
        return agent

    def create_function_call_agent(self, model: str, instructions: str, user_functions: dict):
        """Create an agent with function calling capabilities."""
        # user_functions is a dict of {function_name: function_impl}
        # Convert this to a FunctionTool
        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)

        agent = self.create_agent(model=model, instructions=instructions, toolset=toolset)
        return agent

    def create_agent_with_tool_resources(self, model: str, instructions: str, tool, tool_resources: List[dict]):
        """Create an agent with a given tool and tool resources."""
        # `tool` should provide .definitions (like FileSearchTool or CodeInterpreterTool)
        agent = self.create_agent(model=model, instructions=instructions,
                                  tools=tool.definitions, tool_resources=tool_resources)
        return agent

    def create_message_with_file_attachment(self, thread_id: str, file_id: str, content: str):
        """Create a user message with a file search attachment."""
        # Attachments require tools definitions, here we use FileSearchTool's definitions
        file_search_tool = FileSearchTool()
        attachment = MessageAttachment(file_id=file_id, tools=file_search_tool.definitions)
        message = self.create_message(thread_id=thread_id, role="user", content=content, attachments=[attachment])
        return message

    def create_message_with_code_interpreter_attachment(self, thread_id: str, file_id: str, content: str):
        """Create a user message with a code interpreter attachment."""
        code_tool = CodeInterpreterTool()
        attachment = MessageAttachment(file_id=file_id, tools=code_tool.definitions)
        message = self.create_message(thread_id=thread_id, role="user", content=content, attachments=[attachment])
        return message

    def retrieve_latest_messages(self, thread_id: str):
        """Retrieve and print latest messages with their text content."""
        messages = self.list_messages(thread_id=thread_id)
        return messages

    def retrieve_files_from_messages(self, thread_id: str):
        """Retrieve files referenced in messages and save them."""
        messages = self.get_messages(thread_id=thread_id)

        # Save image files if any
        for image_content in messages.image_contents:
            file_id = image_content.image_file.file_id
            file_name = f"{file_id}_image_file.png"
            self.save_file(file_id=file_id, target_name=file_name)
            print(f"Saved image file to: {Path.cwd() / file_name}")

        # Save any file path annotations
        for file_path_annotation in messages.file_path_annotations:
            file_id = file_path_annotation.file_path.file_id
            file_name = f"{file_id}_annotated_file"
            self.save_file(file_id=file_id, target_name=file_name)
            print(f"Saved annotated file to: {Path.cwd() / file_name}")



# Example usage
if __name__ == "__main__":
    # Make sure to set the PROJECT_CONNECTION_STRING environment variable
    connection_str = os.environ["FOUNDRY_PROJECT"]

    wrapper = AIAgentWrapper(connection_string=connection_str)

    # Example: Create a basic agent with a code interpreter tool
    code_tool = CodeInterpreterTool()
    agent = wrapper.create_agent(
        model="gpt-4-1106-preview",
        instructions="You are a helpful assistant",
        tools=code_tool.definitions
    )
    print("Agent created:", agent.id)

    # Create a thread
    thread = wrapper.create_thread()
    print("Thread created:", thread.id)

    # Send a user message
    user_msg = wrapper.create_message(
        thread_id=thread.id,
        role="user",
        content="Hello, can you tell me a joke?"
    )
    print("User message created:", user_msg.id)

    # Process the message (blocking)
    run = wrapper.create_and_process_run(thread_id=thread.id, assistant_id=agent.id)
    print("Run completed. Status:", run.status)

    # Retrieve messages
    wrapper.list_messages(thread_id=thread.id)

    # Clean up
    wrapper.delete_agent(agent.id)
    print("Agent deleted.")
