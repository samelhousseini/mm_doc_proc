#!/bin/bash

# This script runs before the azd provision step
# It helps set up the right parameters based on whether you want to create a new OpenAI resource
# or use an existing one

# Default to creating a new OpenAI resource if not specified
if [ -z "$AZURE_OPENAI_CREATE" ]; then
  echo "AZURE_OPENAI_CREATE not set, defaulting to creating a new OpenAI resource"
  export AZURE_OPENAI_CREATE=true
fi

# Check if we're using an existing OpenAI resource
if [ "$AZURE_OPENAI_CREATE" = "false" ]; then
  echo "Using existing OpenAI resource"
  
  # Validate required parameters for using an existing resource
  if [ -z "$AZURE_OPENAI_API_KEY" ] || [ -z "$AZURE_OPENAI_ENDPOINT" ]; then
    echo "ERROR: When using an existing OpenAI resource (AZURE_OPENAI_CREATE=false), you must set both:"
    echo "  AZURE_OPENAI_API_KEY  - The API key for your existing OpenAI resource"
    echo "  AZURE_OPENAI_ENDPOINT - The endpoint URL for your existing OpenAI resource"
    exit 1
  fi

  echo "Using OpenAI endpoint: $AZURE_OPENAI_ENDPOINT"
  # Don't print the API key for security reasons
  echo "OpenAI API key is set"

else
  echo "Creating a new OpenAI resource"
  
  # Set a default name if not specified
  if [ -z "$AZURE_OPENAI_RESOURCE_NAME" ]; then
    export AZURE_OPENAI_RESOURCE_NAME="${AZURE_ENV_NAME}-openai"
    echo "AZURE_OPENAI_RESOURCE_NAME not set, using default: $AZURE_OPENAI_RESOURCE_NAME"
  else
    echo "Using OpenAI resource name: $AZURE_OPENAI_RESOURCE_NAME"
  fi
fi

echo "Pre-provision hook completed successfully"