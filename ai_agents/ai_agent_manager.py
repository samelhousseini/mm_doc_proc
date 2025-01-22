import os
from PIL import Image
from typing import Optional, List, Any, Dict
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RunStatus,
    AgentEventHandler,
    MessageDeltaTextContent,
    MessageTextContent,
    FilePurpose,
    ThreadMessage,
    ThreadMessageOptions,
    TruncationObject,
    ThreadRun,
    RunStep,
    MessageRole,
)
from azure.identity import DefaultAzureCredential

from opentelemetry import trace
from azure.monitor.opentelemetry import configure_azure_monitor

# Tools
from azure.ai.projects.models import (
    BingGroundingTool,
    AzureAISearchTool,
    CodeInterpreterTool,
    FileSearchTool
)

# Import your data models
from ai_agent_data_models import (
    AgentConfiguration,
    ChatMessage,
    ChatRunStep,
    ChatResponse,
)

from rich.console import Console
console = Console()


class MyEventHandler(AgentEventHandler):
    """Event handler for streaming runs (optional)."""
    def on_message_delta(self, delta):
        for content_part in delta.delta.content:
            if isinstance(content_part, MessageDeltaTextContent) and content_part.text:
                print(f"[Stream delta] {content_part.text.value}")

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


class AIAgentManager:
    """
    A higher-level wrapper for Azure AI Project Agents with simpler usage:
      - Auto-creates (or retrieves) an Agent by name if it doesn't exist.
      - Supports single-turn chat() or multi-turn chat_in_thread().
      - Tools are automatically enabled based on the AgentConfiguration.
      - Azure Monitor tracing is enabled by default (if your project supports it).
    """

    def __init__(self, connection_string: str, config: AgentConfiguration):
        self.config = config
        self.client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(),
            conn_str=connection_string
        )

        application_insights_connection_string = self.client.telemetry.get_connection_string()
        if application_insights_connection_string:
            configure_azure_monitor(connection_string=application_insights_connection_string)
            self.tracer = trace.get_tracer(__name__)
        else:
            print("Application Insights is not enabled for this project.")
            print("Enable it via the 'Tracing' tab in your AI Foundry project page.")
            self.tracer = None

        self.agent = self._get_or_create_agent()

    def _get_or_create_agent(self):
        agents_list = self.client.agents.list_agents()
        found_agent = None
        for item in agents_list.data:
            if item["name"] == self.config.name:
                found_agent = item
                break

        if found_agent:
            agent_id = found_agent["id"]
            console.print(f"Found existing agent: {agent_id}")
            return self.client.agents.get_agent(agent_id)
        else:
            tools_definitions = []
            resources = None

            # Bing
            if self.config.enable_bing and self.config.bing_connection_name:
                bing_conn = self.client.connections.get(connection_name=self.config.bing_connection_name)
                bing_tool = BingGroundingTool(connection_id=bing_conn.id)
                tools_definitions.extend(bing_tool.definitions)

            # Azure AI Search
            if (
                self.config.enable_azure_search
                and self.config.azure_search_connection_name
                and self.config.azure_search_index_name
            ):
                search_conn = self.client.connections.get(connection_name=self.config.azure_search_connection_name)
                ai_search_tool = AzureAISearchTool(
                    index_connection_id=search_conn.id,
                    index_name=self.config.azure_search_index_name
                )
                tools_definitions.extend(ai_search_tool.definitions)
                if ai_search_tool.resources:
                    resources = ai_search_tool.resources

            # Code Interpreter
            if self.config.enable_code_interpreter:
                code_tool = CodeInterpreterTool()
                tools_definitions.extend(code_tool.definitions)
                # Merge resources if needed
                if code_tool.resources:
                    if resources is None:
                        resources = code_tool.resources
                    else:
                        resources.code_interpreter = code_tool.resources.code_interpreter

            # File Search
            if self.config.enable_file_search:
                fs_tool = FileSearchTool(vector_store_ids=self.config.vector_store_ids or [])
                tools_definitions.extend(fs_tool.definitions)
                if fs_tool.resources:
                    if resources is None:
                        resources = fs_tool.resources
                    else:
                        resources.file_search = fs_tool.resources.file_search

            new_agent = self.client.agents.create_agent(
                model=self.config.model,
                name=self.config.name,
                instructions=self.config.instructions,
                tools=tools_definitions if tools_definitions else None,
                tool_resources=resources if resources else None,
                temperature=self.config.temperature,
                top_p=self.config.top_p
            )
            return new_agent

    # -----------------------------------------------
    # 1) A quick single-turn chat that always
    #    creates a new thread each time.
    # -----------------------------------------------
    def chat(self, user_message: str, stream: bool = False) -> ChatResponse:
        """
        Single-turn usage. Creates a brand new thread every time.
        """
        span_name = f"chat_with_{self.config.name}"
        if self.tracer:
            with self.tracer.start_as_current_span(span_name):
                return self._chat_impl(user_message, stream)
        else:
            return self._chat_impl(user_message, stream)

    def _chat_impl(self, user_message: str, stream: bool) -> ChatResponse:
        # 1. Create new thread
        thread = self.client.agents.create_thread()
        thread_id = thread.id

        # 2. Create user message
        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # 3. Run
        run_id, run_status = self._run_agent(thread_id, stream=stream)

        # 4. Build chat response
        return self._build_chat_response(thread_id=thread_id, run_id=run_id, run_status=run_status)


    # -----------------------------------------------
    # 2) Methods for multi-turn usage
    # -----------------------------------------------
    def create_new_thread(self) -> str:
        """
        Create a new thread for a fresh conversation, 
        and return the thread ID.
        """
        thread = self.client.agents.create_thread()
        console.print(f"[bold green]Created new thread: {thread.id}[/bold green]")
        return thread.id

    def chat_in_thread(self, thread_id: str, user_message: str, stream: bool = False) -> ChatResponse:
        """
        Append a user message to an existing thread, run the agent,
        and return a ChatResponse for that thread.
        """
        span_name = f"chat_in_thread_{thread_id}"
        if self.tracer:
            with self.tracer.start_as_current_span(span_name):
                return self._chat_in_thread_impl(thread_id, user_message, stream)
        else:
            return self._chat_in_thread_impl(thread_id, user_message, stream)

    def _chat_in_thread_impl(self, thread_id: str, user_message: str, stream: bool) -> ChatResponse:
        # Verify thread exists
        thread_obj = self.client.agents.get_thread(thread_id=thread_id)
        if not thread_obj:
            raise ValueError(f"No thread found with ID: {thread_id}")

        # Create user message
        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Run
        run_id, run_status = self._run_agent(thread_id, stream=stream)

        # Build response
        return self._build_chat_response(thread_id=thread_id, run_id=run_id, run_status=run_status)

    def _run_agent(self, thread_id: str, stream: bool) -> (Optional[str], str):
        """
        Helper method to either do streaming or blocking run,
        and return (run_id, run_status).
        """
        if stream:
            event_handler = MyEventHandler()
            with self.client.agents.create_stream(
                thread_id=thread_id,
                assistant_id=self.agent.id,
                event_handler=event_handler
            ) as stream_handle:
                stream_handle.until_done()

            runs = self.client.agents.list_runs(thread_id=thread_id)
            if runs.data:
                last_run = runs.data[-1]
                return (last_run.get("id"), last_run.get("status", "unknown"))
            else:
                return (None, "unknown")
        else:
            run = self.client.agents.create_and_process_run(thread_id=thread_id, assistant_id=self.agent.id)
            return (run.id, run.status)

    def _build_chat_response(self, thread_id: str, run_id: Optional[str], run_status: str) -> ChatResponse:
        """
        Gathers final messages, run steps, and file references for the thread,
        returning a ChatResponse.
        """
        # 1. Gather messages
        messages_response = self.client.agents.list_messages(thread_id=thread_id)
        chat_messages: List[ChatMessage] = []
        for m in messages_response.data:
            full_text = ""
            for c in m["content"]:
                if isinstance(c, MessageTextContent):
                    full_text += c.text.value
            chat_messages.append(ChatMessage(role=m["role"], content=full_text))

        # 2. Gather run steps
        runs_data = self.client.agents.list_runs(thread_id=thread_id).data
        latest_run_id = runs_data[-1]["id"] if runs_data else None
        run_steps_data = []
        if latest_run_id:
            steps_data = self.client.agents.list_run_steps(thread_id=thread_id, run_id=latest_run_id)
            run_steps_data = steps_data.data if steps_data and steps_data.data else []

        run_steps: List[ChatRunStep] = [
            ChatRunStep(step_type=step["type"], status=step["status"])
            for step in run_steps_data
        ]

        # 3. Identify images/files from the thread's messages
        thread_msgs = self.client.agents.list_messages(thread_id=thread_id)
        file_ids = []
        for image_content in thread_msgs.image_contents:
            file_id = image_content.image_file.file_id
            file_ids.append(file_id)
        for fa in thread_msgs.file_path_annotations:
            file_ids.append(fa.file_path.file_id)

        # 4. Optionally download them right away, or skip if you only want references
        downloaded_paths = self.collect_generated_files(thread_id=thread_id)

        # Return ChatResponse
        return ChatResponse(
            agent_id=self.agent.id,
            thread_id=thread_id,
            run_id=run_id,
            status=run_status,
            messages=chat_messages,
            run_steps=run_steps,
            file_ids=file_ids,
            downloaded_files=downloaded_paths
        )

    # -------------------------------------------------
    # Extra helper: collect/download files in this thread
    # -------------------------------------------------
    def collect_generated_files(
        self,
        thread_id: str,
        target_dir: str = "./downloaded_files",
        display_images: bool = False
    ) -> List[str]:
        """
        Similar to the official sample, parse images/files from messages 
        in the given thread, download them locally, and optionally display images.
        Returns a list of local file paths.
        """
        os.makedirs(target_dir, exist_ok=True)
        file_paths = []

        messages = self.client.agents.list_messages(thread_id=thread_id)

        # images
        for image_content in messages.image_contents:
            file_id = image_content.image_file.file_id
            file_name = f"{file_id}_image.png"
            local_path = os.path.join(target_dir, file_name)
            self.client.agents.save_file(file_id=file_id, file_name=file_name, target_dir=target_dir)
            file_paths.append(local_path)
            print(f"[Images] Downloaded: {local_path}")

            if display_images:
                try:
                    Image.open(local_path).show()
                except Exception as e:
                    print(f"Error displaying image: {e}")

        # annotated files
        for fa in messages.file_path_annotations:
            file_id = fa.file_path.file_id
            file_name = f"{file_id}_annotated"
            local_path = os.path.join(target_dir, file_name)
            self.client.agents.save_file(file_id=file_id, file_name=file_name, target_dir=target_dir)
            file_paths.append(local_path)
            print(f"[Files] Downloaded: {local_path}")

        return file_paths

    # -------------------------------------------------
    # Single-file or multi-file download by ID
    # -------------------------------------------------
    def download_files(
        self,
        file_ids: List[str],
        target_dir: str = "./downloaded_files",
        display_images: bool = True
    ) -> None:
        """
        Download files by file_id, if permissible.
        """
        os.makedirs(target_dir, exist_ok=True)

        for fid in file_ids:
            file_info = self.client.agents.get_file(fid)
            console.print("FileInfo: ", file_info)

            # Only certain file 'purpose' are allowed for download
            if file_info.purpose in [
                FilePurpose.FINE_TUNE_RESULTS,
                FilePurpose.AGENTS_OUTPUT,
                FilePurpose.BATCH_OUTPUT
            ]:
                filename = file_info.get("filename") or f"{fid}.dat"
                local_path = os.path.join(target_dir, filename)
                self.client.agents.save_file(file_id=fid, file_name=filename, target_dir=target_dir)
                print(f"Downloaded file: {local_path}")

                if display_images:
                    try:
                        ext = filename.lower().split(".")[-1]
                        if ext in {"png", "jpg", "jpeg", "gif", "bmp", "tiff"}:
                            Image.open(local_path).show()
                    except Exception as e:
                        print(f"Could not display image: {e}")
            else:
                print(f"File {fid} has purpose={file_info.purpose}, not downloadable.")


    def delete_agent(self):
        """If you explicitly want to delete the agent from Azure."""
        self.client.agents.delete_agent(self.agent.id)


# ------------------------------------------------------------------
# Example Usage
# ------------------------------------------------------------------
if __name__ == "__main__":
    from ai_agent_data_models import AgentConfiguration

    PROJECT_CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING", "<your_connection_string>")

    config = AgentConfiguration(
        name="my-fancy-bot",
        model="gpt-4",
        instructions="You are a helpful data analysis assistant.",
        enable_bing=True,
        bing_connection_name="bing-grounding",
        enable_code_interpreter=True,
        enable_azure_search=True,
        azure_search_connection_name="searchseh00031",
        azure_search_index_name="document-content-search-units-large",
        enable_file_search=True,
        vector_store_ids=["<some_vector_store_id>"],
        temperature=0.7,
        top_p=0.95
    )

    manager = AIAgentManager(connection_string=PROJECT_CONNECTION_STRING, config=config)

    # 1) Single-turn conversation
    single_turn_response = manager.chat("Give me a quick summary on the weather.")
    print("Single-turn run status:", single_turn_response.status)

    # 2) Multi-turn usage
    new_tid = manager.create_new_thread()
    response1 = manager.chat_in_thread(new_tid, "Let's talk about stock prices.")
    print("Multi-turn run status:", response1.status)

    # next user message, same thread
    response2 = manager.chat_in_thread(new_tid, "Now show me a bar chart of trading volumes.")
    print("Multi-turn run status:", response2.status)

    # Clean up if needed
    # manager.delete_agent()
