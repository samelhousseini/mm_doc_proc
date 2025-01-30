import os
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.append('../')
sys.path.append('../ai_agents')
sys.path.append('../ai_agents/azure_ai_agents')

from utils.file_utils import * 
from utils.text_utils import *
from utils.openai_utils import *

from multimodal_processing_pipeline.data_models import *
from multimodal_processing_pipeline.pipeline_utils import *
from multimodal_processing_pipeline.pdf_ingestion_pipeline import *

from search.search_data_models import *
from search.azure_ai_index_builder import *
from search.configure_ai_search import *
from search.search_data_models import *
from search.search_helpers import *

from ai_agents.azure_ai_agents.ai_agent_manager import *
from ai_agents.azure_ai_agents.ai_agent_data_models import *

from rich.console import Console
console = Console()


module_directory = os.path.dirname(os.path.abspath(__file__))


def locate_search_prompt(prompt_name, module_directory=module_directory):
    return locate_prompt(prompt_name, module_directory)


agent_manager = AIAgentManager()





class MultimodalSearch():

    def __init__(self, search_config: AISearchConfig):
        self.document = None
        self.index_builder = None
        self.search_config = search_config
        self.index_builder =  DynamicAzureIndexBuilder(self.search_config)


    def format_search_unit(self, search_unit: SearchUnit, index: int) -> str:
        """
        Return a nicely formatted, multiline string representation of the SearchUnit,
        ignoring paths and vectors.
        """
        metadata = search_unit.metadata
        
        lines = [
            "SearchUnit Information",
            "----------------------",
            f"Reference ID:      {index}",
            f"Filename:          {metadata.filename}",
            f"Total Pages:       {metadata.total_pages}",
            f"Processed Pages:   {metadata.processed_pages}",
            f"Page Number:       {search_unit.page_number}",
            f"Unit Type:         {search_unit.unit_type}",
            "",
            "Extracted Text",
            "--------------",
            search_unit.text or "(no text)",
        ]
        
        return "\n".join(lines)
    

    def format_search_result(self, search_result: SearchResult) -> str:
        """
        Return a nicely formatted, multiline string representation of the SearchResult,
        ignoring any potential paths or vectors (not present in this model).
        """
        lines = [
            "SearchResult",
            "============",
            f"Final Answer: {search_result.final_answer}",
            "",
            "Tables",
            "------"
        ]

        # Append tables to the output
        for index, table in enumerate(search_result.table_list, start=1):
            lines.append(f"{index}. {table}")

        return "\n".join(lines)

    def hybrid_search(self, 
                      query: str, 
                      search_params: SearchParams = SearchParams()
                      ):     
        results = self.index_builder.hybrid_search(query=query, search_params=search_params)
        return [SearchUnit(r) for r in results]


    
    def wide_search(self, 
                    query: str, 
                    search_params: SearchParams = SearchParams(),
                    model_info: TextProcessingModelnfo = TextProcessingModelnfo(),
                    ):     
        
        results = self.index_builder.wide_search(query=query, search_params=search_params, model_info=model_info)
        return [SearchUnit.model_validate(r) for r in results]
    

    def multimodal_search(self, 
                          query: str, 
                          search_params: SearchParams = SearchParams(),
                          model_info: TextProcessingModelnfo = TextProcessingModelnfo()
                          ):     
                
        results = self.wide_search(query=query, search_params=search_params, model_info=model_info)
        context = "\n\n".join([f"\n{self.format_search_unit(r, i)}\n" for i, r in enumerate(results)])

        search_prompt_template = read_asset_file(locate_search_prompt('multimodal_search_prompt.txt'))[0]
        prompt = search_prompt_template.format(query=query, context=context)

        answer = call_llm_structured_outputs(
            prompt,
            model_info=model_info,
            response_format=SearchResult
        )

        search_response = MultiModalSearchResponse(search_response=answer)

        if search_params.use_code_interpreter:
            background_info = self.format_search_result(answer)
            ai_agent_prompt = read_asset_file(locate_search_prompt('ai_agent_prompt.txt'))[0]
            ai_agent_prompt = ai_agent_prompt.format(query=query, context=background_info)
            console.print("\n\nAI Agent Prompt:\n", ai_agent_prompt)
            response = agent_manager.chat_in_thread(user_message=ai_agent_prompt)
            search_response.agent_response = response

        
        return search_response