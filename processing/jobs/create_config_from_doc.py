#!/usr/bin/env python
"""
Document Configuration Creator

This script uploads a local document to Azure Blob Storage and creates a
ProcessingPipelineConfiguration with the blob URL as the PDF path.
It saves the configuration as JSON to the upload JSON container.
"""

import os
import sys
import json
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from storage.azure_blob_storage import AzureBlobStorage
from multimodal_processing_pipeline.configuration_models import ProcessingPipelineConfiguration
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration from environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME", "data")
AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME", "data")

def create_config_from_document(
    local_file_path: str, 
    config_name: Optional[str] = None
) -> str:
    """
    Upload a local document to Azure Blob Storage, create a ProcessingPipelineConfiguration
    with the blob URL as the PDF path, and save the configuration as JSON to the upload JSON container.
    
    Args:
        local_file_path: Path to the local document file
        config_name: Optional name for the configuration file. If None, uses the document name with .json extension
    
    Returns:
        The URL of the uploaded configuration JSON file
    """
    # Initialize Azure Blob Storage
    storage = AzureBlobStorage(account_name=AZURE_STORAGE_ACCOUNT_NAME)
    
    # Ensure local file exists
    local_path = Path(local_file_path)
    if not local_path.exists():
        raise FileNotFoundError(f"Document file not found: {local_file_path}")
    
    logger.info(f"Uploading document: {local_file_path}")
    
    # Create document container if it doesn't exist
    storage.create_container(AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME)
    
    # Upload the document to Azure Blob Storage
    document_blob_name = local_path.name
    document_url = storage.upload_blob(
        AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME,
        document_blob_name,
        str(local_path)
    )
    
    logger.info(f"Document uploaded to: {document_url}")
    
    # Create a basic ProcessingPipelineConfiguration with default values
    config = ProcessingPipelineConfiguration(
        pdf_path=document_url,
        output_directory=None,  # Will be determined by the processing job
        resume_processing_if_interrupted=True,
        process_pages_as_jpg=True,
        process_text=True,
        process_images=True,
        process_tables=True,
        save_text_files=True,
        generate_condensed_text=True,
        generate_table_of_contents=True,
        translate_full_text=[],
        translate_condensed_text=[],
        custom_page_processing_steps=[],
        custom_document_processing_steps=[]
    )
    
    # Generate config name if not provided
    if not config_name:
        config_name = f"{local_path.stem}_config.json"
    elif not config_name.endswith('.json'):
        config_name += '.json'
    
    # Convert config to JSON
    config_json = config.to_json()
    
    # Save JSON locally first
    local_json_path = os.path.join(os.getcwd(), config_name)
    with open(local_json_path, 'w') as f:
        json.dump(config_json, f, indent=2)
    
    logger.info(f"Configuration JSON saved locally to: {local_json_path}")
    
    # Create JSON container if it doesn't exist
    storage.create_container(AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME)
    
    # Upload the JSON to Azure Blob Storage
    json_url = storage.upload_blob(
        AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME,
        config_name,
        local_json_path
    )
    
    logger.info(f"Configuration JSON uploaded to: {json_url}")
    
    return json_url

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Upload a document and create a processing configuration.')
    parser.add_argument('file_path', help='Path to the local document file')
    parser.add_argument('--name', help='Name for the configuration file (optional)', default=None)
    
    args = parser.parse_args()
    
    try:
        config_url = create_config_from_document(args.file_path, args.name)
        print(f"Successfully created and uploaded configuration: {config_url}")
    except Exception as e:
        logger.error(f"Error creating configuration: {str(e)}")
        sys.exit(1)
    
    sys.exit(0)