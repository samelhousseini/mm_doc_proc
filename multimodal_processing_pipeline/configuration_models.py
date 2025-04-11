import os
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Type, Union, Any

from utils.openai_data_models import *
from multimodal_processing_pipeline.data_models import *



class CustomProcessingStep(BaseModel):
    """
    Custom processing step for a page.
    """
    name: str
    prompt: str
    data_model: Optional[Any] = None
    ai_model: Optional[Union[TextProcessingModelnfo, MulitmodalProcessingModelInfo]] = MulitmodalProcessingModelInfo()




class ProcessingPipelineConfiguration(BaseModel):
    """
    Configuration settings for the processing pipeline.
    """
    pdf_path: str
    output_directory: Optional[str] = None
    resume_processing_if_interrupted: bool = True # If True, will resume processing from the last saved state
    multimodal_model: MulitmodalProcessingModelInfo = MulitmodalProcessingModelInfo()
    text_model: TextProcessingModelnfo = TextProcessingModelnfo()
    process_pages_as_jpg: bool = True
    process_text: bool = True
    process_images: bool = True
    process_tables: bool = True
    custom_page_processing_steps: List[CustomProcessingStep] = []
    save_text_files: bool = True
    generate_condensed_text: bool = False
    generate_table_of_contents: bool = False
    translate_full_text: List[str] = []
    translate_condensed_text: List[str] = []
    custom_document_processing_steps: List[CustomProcessingStep] = []
    
    # Allow arbitrary types in the model
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def to_json(self) -> dict:
        """Convert the configuration to a JSON-serializable dictionary."""
        # Use model_dump to get the basic dictionary
        data = self.model_dump()
        # Set client to None to make it serializable
        if 'multimodal_model' in data and data['multimodal_model']:
            data['multimodal_model']['client'] = None
        if 'text_model' in data and data['text_model']:
            data['text_model']['client'] = None
            
        # Handle client in custom processing steps
        if 'custom_page_processing_steps' in data:
            for step in data['custom_page_processing_steps']:
                if 'ai_model' in step and step['ai_model']:
                    step['ai_model']['client'] = None
                    
        if 'custom_document_processing_steps' in data:
            for step in data['custom_document_processing_steps']:
                if 'ai_model' in step and step['ai_model']:
                    step['ai_model']['client'] = None
        
        return data
    
    def save_to_json(self, filepath: str) -> None:
        """Save the configuration to a JSON file."""
        import json
        with open(filepath, 'w') as f:
            json.dump(self.to_json(), f, indent=2)
    
    @classmethod
    def from_json_dict(cls, config_json: dict) -> 'ProcessingPipelineConfiguration':
        """
        Create a ProcessingPipelineConfiguration from a JSON dictionary.
        
        Args:
            config_json: Dictionary containing the configuration parameters
            
        Returns:
            A fully initialized ProcessingPipelineConfiguration object
        """
        # Initialize the base configuration with primitive fields
        config = cls(
            pdf_path=config_json['pdf_path'],
            output_directory=config_json.get('output_directory'),
            resume_processing_if_interrupted=config_json.get('resume_processing_if_interrupted', True),
            process_pages_as_jpg=config_json.get('process_pages_as_jpg', True),
            process_text=config_json.get('process_text', True),
            process_images=config_json.get('process_images', True),
            process_tables=config_json.get('process_tables', True),
            save_text_files=config_json.get('save_text_files', True),
            generate_condensed_text=config_json.get('generate_condensed_text', False),
            generate_table_of_contents=config_json.get('generate_table_of_contents', False),
            translate_full_text=config_json.get('translate_full_text', []),
            translate_condensed_text=config_json.get('translate_condensed_text', [])
        )
        
        # Initialize multimodal_model if present
        if 'multimodal_model' in config_json and config_json['multimodal_model']:
            mm_json = config_json['multimodal_model']
            config.multimodal_model = MulitmodalProcessingModelInfo(
                provider=mm_json.get('provider', 'azure'),
                model_name=mm_json.get('model_name', 'gpt-4o'),
                reasoning_efforts=mm_json.get('reasoning_efforts', 'medium'),
                endpoint=mm_json.get('endpoint', ''),
                key=mm_json.get('key', ''),
                model=mm_json.get('model', ''),
                api_version=mm_json.get('api_version', '2024-12-01-preview')
            )
        
        # Initialize text_model if present
        if 'text_model' in config_json and config_json['text_model']:
            tm_json = config_json['text_model']
            config.text_model = TextProcessingModelnfo(
                provider=tm_json.get('provider', 'azure'),
                model_name=tm_json.get('model_name', 'gpt-4o'),
                reasoning_efforts=tm_json.get('reasoning_efforts', 'medium'),
                endpoint=tm_json.get('endpoint', ''),
                key=tm_json.get('key', ''),
                model=tm_json.get('model', ''),
                api_version=tm_json.get('api_version', '2024-12-01-preview')
            )
        
        # Initialize custom_page_processing_steps if present
        if 'custom_page_processing_steps' in config_json and config_json['custom_page_processing_steps']:
            config.custom_page_processing_steps = []
            for step_json in config_json['custom_page_processing_steps']:
                # Initialize AI model for the step if present
                ai_model = None
                if 'ai_model' in step_json and step_json['ai_model']:
                    model_json = step_json['ai_model']
                    if model_json.get('model_name') in ["gpt-4o", "gpt-45", "o1"]:
                        ai_model = MulitmodalProcessingModelInfo(
                            provider=model_json.get('provider', 'azure'),
                            model_name=model_json.get('model_name', 'gpt-4o'),
                            reasoning_efforts=model_json.get('reasoning_efforts', 'medium'),
                            endpoint=model_json.get('endpoint', ''),
                            key=model_json.get('key', ''),
                            model=model_json.get('model', ''),
                            api_version=model_json.get('api_version', '2024-12-01-preview')
                        )
                    else:
                        ai_model = TextProcessingModelnfo(
                            provider=model_json.get('provider', 'azure'),
                            model_name=model_json.get('model_name', 'gpt-4o'),
                            reasoning_efforts=model_json.get('reasoning_efforts', 'medium'),
                            endpoint=model_json.get('endpoint', ''),
                            key=model_json.get('key', ''),
                            model=model_json.get('model', ''),
                            api_version=model_json.get('api_version', '2024-12-01-preview')
                        )
                
                config.custom_page_processing_steps.append(
                    CustomProcessingStep(
                        name=step_json.get('name', ''),
                        prompt=step_json.get('prompt', ''),
                        data_model=step_json.get('data_model'),
                        ai_model=ai_model
                    )
                )
        
        # Initialize custom_document_processing_steps if present
        if 'custom_document_processing_steps' in config_json and config_json['custom_document_processing_steps']:
            config.custom_document_processing_steps = []
            for step_json in config_json['custom_document_processing_steps']:
                # Initialize AI model for the step if present
                ai_model = None
                if 'ai_model' in step_json and step_json['ai_model']:
                    model_json = step_json['ai_model']
                    if model_json.get('model_name') in ["gpt-4o", "gpt-45", "o1"]:
                        ai_model = MulitmodalProcessingModelInfo(
                            provider=model_json.get('provider', 'azure'),
                            model_name=model_json.get('model_name', 'gpt-4o'),
                            reasoning_efforts=model_json.get('reasoning_efforts', 'medium'),
                            endpoint=model_json.get('endpoint', ''),
                            key=model_json.get('key', ''),
                            model=model_json.get('model', ''),
                            api_version=model_json.get('api_version', '2024-12-01-preview')
                        )
                    else:
                        ai_model = TextProcessingModelnfo(
                            provider=model_json.get('provider', 'azure'),
                            model_name=model_json.get('model_name', 'gpt-4o'),
                            reasoning_efforts=model_json.get('reasoning_efforts', 'medium'),
                            endpoint=model_json.get('endpoint', ''),
                            key=model_json.get('key', ''),
                            model=model_json.get('model', ''),
                            api_version=model_json.get('api_version', '2024-12-01-preview')
                        )
                
                config.custom_document_processing_steps.append(
                    CustomProcessingStep(
                        name=step_json.get('name', ''),
                        prompt=step_json.get('prompt', ''),
                        data_model=step_json.get('data_model'),
                        ai_model=ai_model
                    )
                )
        
        return config
    
    @classmethod
    def from_json(cls, filepath: str) -> 'ProcessingPipelineConfiguration':
        """Load the configuration from a JSON file."""
        import json
        with open(filepath, 'r') as f:
            config_json = json.load(f)
        return cls.from_json_dict(config_json)