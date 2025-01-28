import os
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Type, Union


from data_models import *


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
    save_text_files: bool = True
    generate_condensed_text: bool = False
    generate_table_of_contents: bool = False
    translate_full_text: List[str] = []
    translate_condensed_text: List[str] = []
