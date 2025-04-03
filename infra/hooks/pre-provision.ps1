# This script runs before the azd provision step
# It helps set up the right parameters based on whether you want to create a new OpenAI resource
# or use an existing one

# Default to creating a new OpenAI resource if not specified
if (-not $env:AZURE_OPENAI_CREATE) {
  Write-Host "AZURE_OPENAI_CREATE not set, defaulting to creating a new OpenAI resource"
  $env:AZURE_OPENAI_CREATE = "true"
}

# Check if we're using an existing OpenAI resource
if ($env:AZURE_OPENAI_CREATE -eq "false") {
  Write-Host "Using existing OpenAI resource"
  
  # Validate required parameters for using an existing resource
  if (-not $env:AZURE_OPENAI_API_KEY -or -not $env:AZURE_OPENAI_ENDPOINT) {
    Write-Host "ERROR: When using an existing OpenAI resource (AZURE_OPENAI_CREATE=false), you must set both:"
    Write-Host "  AZURE_OPENAI_API_KEY  - The API key for your existing OpenAI resource"
    Write-Host "  AZURE_OPENAI_ENDPOINT - The endpoint URL for your existing OpenAI resource"
    exit 1
  }

  Write-Host "Using OpenAI endpoint: $env:AZURE_OPENAI_ENDPOINT"
  # Don't print the API key for security reasons
  Write-Host "OpenAI API key is set"
}
else {
  Write-Host "Creating a new OpenAI resource"
  
  # Set a default name if not specified
  if (-not $env:AZURE_OPENAI_RESOURCE_NAME) {
    $env:AZURE_OPENAI_RESOURCE_NAME = "$env:AZURE_ENV_NAME-openai"
    Write-Host "AZURE_OPENAI_RESOURCE_NAME not set, using default: $env:AZURE_OPENAI_RESOURCE_NAME"
  }
  else {
    Write-Host "Using OpenAI resource name: $env:AZURE_OPENAI_RESOURCE_NAME"
  }
}

Write-Host "Pre-provision hook completed successfully"