#!/usr/bin/env python
"""
Document Processing Job
This script processes documents uploaded to the Azure Blob Storage container.
It is triggered by events from the Azure Queue.
"""

import os
import json
import uuid
import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

import azure.storage.blob as blob_storage
from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.cosmos import CosmosClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import Vector
import openai
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
AZURE_STORAGE_UPLOAD_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_CONTAINER_NAME", "data")
AZURE_STORAGE_OUTPUT_CONTAINER_NAME = os.getenv("AZURE_STORAGE_OUTPUT_CONTAINER_NAME", "processed")
STORAGE_QUEUE_NAME = os.getenv("STORAGE_QUEUE_NAME", "doc-process-queue")

# Azure OpenAI Configuration
AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE")
AZURE_OPENAI_KEY_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_KEY_EMBEDDING_LARGE")
AZURE_OPENAI_MODEL_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_MODEL_EMBEDDING_LARGE", "text-embedding-3-large")
AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE", "2024-12-01-preview")

AZURE_OPENAI_RESOURCE_4O = os.getenv("AZURE_OPENAI_RESOURCE_4O")
AZURE_OPENAI_KEY_4O = os.getenv("AZURE_OPENAI_KEY_4O")
AZURE_OPENAI_MODEL_4O = os.getenv("AZURE_OPENAI_MODEL_4O", "gpt-4o-2")
AZURE_OPENAI_API_VERSION_4O = os.getenv("AZURE_OPENAI_API_VERSION_4O", "2024-12-01-preview")

# Azure AI Search Configuration
AZURE_AI_SEARCH_SERVICE_NAME = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME")
AZURE_AI_SEARCH_API_KEY = os.getenv("AZURE_AI_SEARCH_API_KEY")
AZURE_AI_SEARCH_INDEX_NAME = "document-index"

# Cosmos DB Configuration
COSMOS_URI = os.getenv("COSMOS_URI")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME", "KYC")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_CONTAINER_NAME", "Customers")
COSMOS_LOG_CONTAINER = os.getenv("COSMOS_LOG_CONTAINER", "logs")

# App Insights for monitoring
APP_INSIGHTS_CONN_STRING = os.getenv("APP_INSIGHTS_CONN_STRING")

class DocumentProcessor:
    """Document processor handles document extraction, analysis, and storage"""
    
    def __init__(self):
        """Initialize the document processor with all necessary clients"""
        # Azure credentials
        try:
            self.credential = DefaultAzureCredential()
            logger.info("Using DefaultAzureCredential")
        except Exception:
            logger.info