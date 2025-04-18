#!/usr/bin/env python
"""
Local Document Processing Job

This script processes a document locally without using Service Bus.
It creates a ProcessingPipelineConfiguration for a sample PDF file,
runs a DocumentIngestionJob, and outputs the results.
"""

import os
import sys
import uuid
import logging
from pathlib import Path
from dotenv import load_dotenv

# Set up paths for imports
sys.path.append("./")
sys.path.append("../")
sys.path.append("../../")



# Import required modules
from multimodal_processing_pipeline.configuration_models import ProcessingPipelineConfiguration
from search.search_data_models import AISearchConfig
from orchestration.document_ingestion_job import DocumentIngestionJob
from utils.openai_data_models import (
    MulitmodalProcessingModelInfo,
    TextProcessingModelnfo,
    EmbeddingModelnfo  # In case you want an embedding model as well
) 


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


AZURE_STORAGE_OUTPUT_CONTAINER_NAME = os.getenv("AZURE_STORAGE_OUTPUT_CONTAINER_NAME", "processed")


def main():
    """
    Main function to process a PDF file locally
    """
    # Path to the sample PDF file
    sample_pdf_path = os.path.abspath("sample_data/1_London_Brochure.pdf")
    
    if not os.path.exists(sample_pdf_path):
        logger.error(f"Sample PDF file not found: {sample_pdf_path}")
        return
    
    logger.info(f"Processing PDF file: {sample_pdf_path}")
    
    # Create output directory
    output_dir = os.path.abspath("processed")
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate a unique document ID
    document_id = f"london_brochure_{uuid.uuid4().hex[:8]}"
    
    output_dir = os.path.join(output_dir, document_id)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create ProcessingPipelineConfiguration
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=None,
        resume_processing_if_interrupted=True,
        process_pages_as_jpg=True,
        process_text=True,
        process_images=True,
        process_tables=True,
        save_text_files=True,
        generate_condensed_text=True,
        generate_table_of_contents=True
    )
    
    
    config.multimodal_model = MulitmodalProcessingModelInfo(           
        model_name="o4-mini",            
        easoning_efforts="medium",      
    )

    config.text_model = TextProcessingModelnfo(
        model_name="o3", 
        reasoning_efforts="low",
    )

    # Save the configuration to a JSON file
    config_path = os.path.join(output_dir, f"{document_id}_config.json")
    config.save_to_json(config_path)
    logger.info(f"Saved configuration to: {config_path}")
    
    # Create AISearchConfig
    search_config = AISearchConfig(
        index_name="local-document-index",
        convert_post_processing_units=True
    )
    
    # Create and run DocumentIngestionJob
    logger.info("Creating DocumentIngestionJob...")
    job = DocumentIngestionJob(config=config, search_config=search_config)
    
    # Execute the job
    logger.info("Executing job...")
    try:
        document = job.execute_job(container_name=AZURE_STORAGE_OUTPUT_CONTAINER_NAME)
        logger.info(f"Job executed successfully. Document ID: {document.metadata.document_id}")
        
        # Print summary of processed pages
        logger.info(f"Processed {len(document.pages)} pages")
        if document.post_processing_content and document.post_processing_content.condensed_text:
            logger.info("Generated condensed text summary")
        if document.post_processing_content and document.post_processing_content.table_of_contents:
            logger.info("Generated table of contents")
            
        return document
    except Exception as e:
        logger.error(f"Error executing job: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        result = main()
        print("\nPDF processing completed successfully!")
    except Exception as e:
        print(f"\nError processing PDF: {str(e)}")
        sys.exit(1)
    
    sys.exit(0)