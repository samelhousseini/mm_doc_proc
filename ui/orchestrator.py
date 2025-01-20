from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.filters.filter_types import FilterTypes
from semantic_kernel.filters.auto_function_invocation.auto_function_invocation_context import (
    AutoFunctionInvocationContext,
)
from semantic_kernel.functions.function_result import FunctionResult
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from typing import Annotated, List, Optional, Dict

import sys
sys.path.append('../multimodal_processing_pipeline')
sys.path.append('../search')

from IPython.display import Markdown, display

from utils.file_utils import * 
from utils.text_utils import *
from utils.openai_utils import *
from multimodal_processing_pipeline.data_models import (
    TextProcessingModelnfo
)

def get_azure_endpoint(resource):
    return f"https://{resource}.openai.azure.com" if not "https://" in resource else resource



class ChatWithFile():
    
    def __init__(self):
        super().__init__()

    @kernel_function(
        name="chat_with_file",
        description="Opens the container app in the browser."
    )
    async def chat_with_file(self,
        file_path: Annotated[str, "The file path to the document we want to chat with."],
        query: Annotated[str, "The query to ask the document."],
        ) -> Annotated[str, "Returns the answer to the qery."]:

        context = read_asset_file(file_path)[0]
        ui_prompt = read_asset_file('ui_prompts/chat_with_file_prompt.txt')[0]

        prompt = ui_prompt.format(context=context, query=query)
        result = call_llm(
            prompt,
            model_info=TextProcessingModelnfo(model_name="o1", reasoning_efforts="high")
        )

        return result
    


class Orchestrator():

    def __init__(self, client = gpt_4o_model_name) -> None:
        super().__init__()

        # Create a history of the conversation
        self.history = ChatHistory()
        self.logged_messages = []

        self.kernel = Kernel()

        self.kernel.add_service(AzureChatCompletion(
            deployment_name=client['AZURE_OPENAI_MODEL'],
            api_key=client['AZURE_OPENAI_KEY'],
            endpoint=get_azure_endpoint(client['AZURE_OPENAI_RESOURCE']),
            service_id="chat-gpt"
        ))


        self.kernel.add_plugin(
            ChatWithFile(),
            plugin_name="ChatWithFilePlugin",
            description="Chat with a file."
        )

  
        self.chat_completion : AzureChatCompletion = self.kernel.get_service(type=ChatCompletionClientBase)
        self.execution_settings = AzureChatPromptExecutionSettings(tool_choice="auto")
        self.execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

        @self.kernel.filter(FilterTypes.AUTO_FUNCTION_INVOCATION)
        async def auto_function_invocation_filter(context: AutoFunctionInvocationContext, next):
            """A filter that will be called for each function call in the response."""
            print(60*"-")
            print("**Automatic Function Call**")
            print("Plugin:", context.function.plugin_name )
            print(f"Function: {context.function.name}")
            print("Function Arguments", context.arguments)            
            # result = context.function_result
            print(60*"-")

            await next(context)


    async def chat(self, query, connection = None):
        # Terminate the loop if the user says "exit"
        if query == "exit":
            return "Goodbye!", self.logged_messages

        # Add user input to the history
        self.history.add_user_message(query)

        result = (await self.chat_completion.get_chat_message_contents(
            chat_history=self.history,
            settings=self.execution_settings,
            kernel=self.kernel,
            arguments=KernelArguments(),
            temperature=0.2
        ))[0]

        # Add the message from the agent to the chat history
        self.history.add_message(result)

        # Share final results
        return str(result)