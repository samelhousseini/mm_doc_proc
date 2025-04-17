#!/bin/bash

# Script to get credentials from Azure resources deployed with main.bicep
# This script retrieves all necessary environment variables for the document processing solution

# Check if the subscription ID and resource group name are provided as command-line arguments
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <subscription-id> <resource-group-name> [path-to-save-env-file]"
  exit 1
fi

# Set parameters from command-line arguments
SUBSCRIPTION_ID="$1"
RESOURCE_GROUP_NAME="$2"
SAVE_PATH="${3:-.}"  # Default to current directory if no path is provided

# Set the Azure subscription and default resource group
echo "Setting subscription to: $SUBSCRIPTION_ID"
az account set --subscription $SUBSCRIPTION_ID
az configure --defaults group=$RESOURCE_GROUP_NAME location=$(az group show --name $RESOURCE_GROUP_NAME --query "location" -o tsv 2>/dev/null)

# Create output file
ENV_FILE="${SAVE_PATH}/.env.bicep_${RESOURCE_GROUP_NAME}"
> "$ENV_FILE"  # Clear the file if it exists

# Get Azure client ID for current session
CLIENT_ID=$(az account get-access-token --query clientId -o tsv 2>/dev/null | tr -d '[:space:]')

echo "Saving environment file to: $ENV_FILE"

# Initialize counters for each resource type
STORAGE_COUNTER=0
OPENAI_COUNTER=0
SEARCH_COUNTER=0
COSMOS_COUNTER=0
ACR_COUNTER=0
ACA_COUNTER=0
ACA_ENV_COUNTER=0
APP_INSIGHTS_COUNTER=0
SERVICEBUS_COUNTER=0

# Get all resources in the specified resource group
echo "Getting resources from resource group: $RESOURCE_GROUP_NAME"

# Add subscription and resource group info to env file
echo "# Azure Subscription and Resource Group" >> $ENV_FILE
echo "AZURE_SUBSCRIPTION_ID=\"$SUBSCRIPTION_ID\"" >> $ENV_FILE
echo "AZURE_RESOURCE_GROUP=\"$RESOURCE_GROUP_NAME\"" >> $ENV_FILE
echo "AZURE_CLIENT_ID=\"$CLIENT_ID\"" >> $ENV_FILE
LOCATION=$(az group show --name $RESOURCE_GROUP_NAME --query "location" -o tsv 2>/dev/null | tr -d '[:space:]')
echo "AZURE_RG_LOCATION=\"$LOCATION\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# Collect all resources in JSON format for processing
echo "Collecting resources..."

# These commands get a list of all resources with their types in JSON format
resources=$(az resource list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "General Resources: Found $(echo $resources | jq 'length') resources"

# Get specific resource types that we are interested in
cognitive_services=$(az cognitiveservices account list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Cognitive Services: Found $(echo $cognitive_services | jq 'length') resources"

registries=$(az acr list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Container Registries: Found $(echo $registries | jq 'length') resources"

container_apps=$(az containerapp list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Container Apps: Found $(echo $container_apps | jq 'length') resources"

container_apps_env=$(az containerapp env list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Container Apps Environments: Found $(echo $container_apps_env | jq 'length') resources"

storage_accounts=$(az storage account list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Storage Accounts: Found $(echo $storage_accounts | jq 'length') resources"

cosmosdb_resources=$(az cosmosdb list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Cosmos DB: Found $(echo $cosmosdb_resources | jq 'length') resources"

ai_search_services=$(az search service list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "AI Search Services: Found $(echo $ai_search_services | jq 'length') resources"

app_insights=$(az monitor app-insights component list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Application Insights: Found $(echo $app_insights | jq 'length') resources"

servicebus_namespaces=$(az servicebus namespace list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json 2>/dev/null || echo "[]")
echo "Service Bus Namespaces: Found $(echo $servicebus_namespaces | jq 'length') resources"

# Combine all resources
combined_resources=$(echo $resources $cognitive_services $registries $container_apps $container_apps_env $storage_accounts $cosmosdb_resources $ai_search_services $app_insights $servicebus_namespaces | jq -s 'add | unique_by(.Name)')

echo "Total resources identified: $(echo $combined_resources | jq 'length')"

# Process Azure OpenAI resources
echo "# Azure OpenAI Configuration" >> $ENV_FILE
openai_accounts=$(echo $cognitive_services | jq '[.[] | select(.Kind == "OpenAI")]')
openai_count=$(echo $openai_accounts | jq 'length')

echo "AZURE_OPENAI_LOCATION=\"$LOCATION\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# Define unified OpenAI variables
echo "# Unified Azure OpenAI configuration" >> $ENV_FILE
echo "AZURE_OPENAI_RESOURCE=\"\"" >> $ENV_FILE
echo "AZURE_OPENAI_KEY=\"\"" >> $ENV_FILE
echo "AZURE_OPENAI_API_VERSION=\"2024-12-01-preview\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# Define model deployment names
echo "# Model deployment names" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_45=\"gpt-4.5-preview\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_41=\"gpt-4.1\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_4O=\"gpt-4o\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_O3_MINI=\"o3-mini\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_O3=\"o3-mini\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_O1=\"o1\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_O1_MINI=\"o1-mini\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_EMBEDDING_ADA=\"text-embedding-ada-002\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_EMBEDDING_SMALL=\"text-embedding-3-small\"" >> $ENV_FILE
echo "AZURE_OPENAI_MODEL_EMBEDDING_LARGE=\"text-embedding-3-large\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# General OpenAI endpoint
echo "# General OpenAI endpoint" >> $ENV_FILE
echo "AZURE_OPENAI_ENDPOINT=\"\"" >> $ENV_FILE
echo "AZURE_OPENAI_API_VERSION=\"2024-12-01-preview\"" >> $ENV_FILE
echo "AZURE_OPENAI_API_KEY=\"\"" >> $ENV_FILE
echo "" >> $ENV_FILE

if [ "$openai_count" -gt "0" ]; then
  for row in $(echo "${openai_accounts}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing OpenAI resource: $RESOURCE_NAME"
    
    # Get endpoint and key
    OPENAI_ENDPOINT=$(az cognitiveservices account show --name "$RESOURCE_NAME" --resource-group $RESOURCE_GROUP_NAME --query "properties.endpoint" -o tsv 2>/dev/null | tr -d '[:space:]')
    OPENAI_KEY=$(az cognitiveservices account keys list --name "$RESOURCE_NAME" --resource-group $RESOURCE_GROUP_NAME --query "key1" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    if [ -n "$OPENAI_ENDPOINT" ] && [ -n "$OPENAI_KEY" ]; then
      # Update general OpenAI endpoint and key
      sed -i "s|AZURE_OPENAI_ENDPOINT=\"\"|AZURE_OPENAI_ENDPOINT=\"$OPENAI_ENDPOINT\"|" $ENV_FILE
      sed -i "s|AZURE_OPENAI_API_KEY=\"\"|AZURE_OPENAI_API_KEY=\"$OPENAI_KEY\"|" $ENV_FILE
      
      # Set unified variables
      sed -i "s|AZURE_OPENAI_RESOURCE=\"\"|AZURE_OPENAI_RESOURCE=\"$RESOURCE_NAME\"|" $ENV_FILE
      sed -i "s|AZURE_OPENAI_KEY=\"\"|AZURE_OPENAI_KEY=\"$OPENAI_KEY\"|" $ENV_FILE
      
      # Get model deployments
      echo "Getting OpenAI model deployments..."
      DEPLOYMENTS=$(az cognitiveservices account deployment list --name "$RESOURCE_NAME" --resource-group $RESOURCE_GROUP_NAME --query "[].{name:name, model:properties.model.name}" -o json 2>/dev/null || echo "[]")
      
      for deployment_row in $(echo "${DEPLOYMENTS}" | jq -r '.[] | @base64'); do
        _deployment_jq() {
          echo ${deployment_row} | base64 --decode | jq -r ${1} 2>/dev/null
        }
        
        DEPLOYMENT_NAME=$(_deployment_jq '.name')
        MODEL_NAME=$(_deployment_jq '.model')
        
        echo "Found deployment: $DEPLOYMENT_NAME (model: $MODEL_NAME)"
        
        # Match deployment with appropriate variable name pattern and update
        if [[ "$DEPLOYMENT_NAME" == *"gpt-4.5"* || "$MODEL_NAME" == *"gpt-4.5"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_45=\"gpt-4.5-preview\"|AZURE_OPENAI_MODEL_45=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"gpt-4o"* || "$MODEL_NAME" == *"gpt-4o"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_4O=\"gpt-4o\"|AZURE_OPENAI_MODEL_4O=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"o1-mini"* || "$MODEL_NAME" == *"o1-mini"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_O1_MINI=\"o1-mini\"|AZURE_OPENAI_MODEL_O1_MINI=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"o1"* || "$MODEL_NAME" == *"o1"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_O1=\"o1\"|AZURE_OPENAI_MODEL_O1=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"o3-mini"* || "$MODEL_NAME" == *"o3-mini"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_O3_MINI=\"o3-mini\"|AZURE_OPENAI_MODEL_O3_MINI=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"o3"* || "$MODEL_NAME" == *"o3"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_O3=\"o3-mini\"|AZURE_OPENAI_MODEL_O3=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"text-embedding-ada-002"* || "$MODEL_NAME" == *"text-embedding-ada-002"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_EMBEDDING_ADA=\"text-embedding-ada-002\"|AZURE_OPENAI_MODEL_EMBEDDING_ADA=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"text-embedding-3-small"* || "$MODEL_NAME" == *"text-embedding-3-small"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_EMBEDDING_SMALL=\"text-embedding-3-small\"|AZURE_OPENAI_MODEL_EMBEDDING_SMALL=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        elif [[ "$DEPLOYMENT_NAME" == *"text-embedding-3-large"* || "$MODEL_NAME" == *"text-embedding-3-large"* ]]; then
          sed -i "s|AZURE_OPENAI_MODEL_EMBEDDING_LARGE=\"text-embedding-3-large\"|AZURE_OPENAI_MODEL_EMBEDDING_LARGE=\"$DEPLOYMENT_NAME\"|" $ENV_FILE
        fi
      done
    else
      echo "⚠️ Warning: Could not get endpoint or key for OpenAI resource $RESOURCE_NAME"
    fi
  done
else
  echo "# No Azure OpenAI resources found in the resource group" >> $ENV_FILE
fi

# OpenAI Model section (Non-Azure)
echo "# OpenAI Model (Non-Azure)" >> $ENV_FILE
echo "OPENAI_API_KEY=\"\"" >> $ENV_FILE
echo "OPENAI_MODEL_4O=\"gpt-4o\"" >> $ENV_FILE
echo "OPENAI_MODEL_O3=\"o3\"" >> $ENV_FILE
echo "OPENAI_MODEL_O3_MINI=\"o3-mini\"" >> $ENV_FILE
echo "OPENAI_MODEL_O1=\"o1\"" >> $ENV_FILE
echo "OPENAI_MODEL_O1_MINI=\"o1-mini\"" >> $ENV_FILE
echo "OPENAI_MODEL_EMBEDDING=\"text-embedding-3-large\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# Get Azure AI Search resources
echo "# Azure AI Search" >> $ENV_FILE
search_count=$(echo $ai_search_services | jq 'length')

if [ "$search_count" -gt "0" ]; then
  for row in $(echo "${ai_search_services}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing AI Search resource: $RESOURCE_NAME"
    
    # Get key
    SEARCH_KEY=$(az search admin-key show --resource-group $RESOURCE_GROUP_NAME --service-name $RESOURCE_NAME --query "primaryKey" -o tsv 2>/dev/null | tr -d '[:space:]')
    SEARCH_ENDPOINT="https://${RESOURCE_NAME}.search.windows.net"
    
    if [ -n "$SEARCH_KEY" ]; then
      echo "AZURE_AI_SEARCH_SERVICE_NAME=\"$SEARCH_ENDPOINT\"" >> $ENV_FILE
      echo "AZURE_AI_SEARCH_API_KEY=\"$SEARCH_KEY\"" >> $ENV_FILE
    else
      echo "⚠️ Warning: Could not get admin key for AI Search resource $RESOURCE_NAME"
      echo "AZURE_AI_SEARCH_SERVICE_NAME=\"$SEARCH_ENDPOINT\"" >> $ENV_FILE
      echo "AZURE_AI_SEARCH_API_KEY=\"\"" >> $ENV_FILE
    fi
  done
else
  echo "AZURE_AI_SEARCH_SERVICE_NAME=\"\"" >> $ENV_FILE
  echo "AZURE_AI_SEARCH_API_KEY=\"\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Get Storage Account resources
echo "# Azure Storage Account" >> $ENV_FILE
storage_count=$(echo $storage_accounts | jq 'length')

if [ "$storage_count" -gt "0" ]; then
  for row in $(echo "${storage_accounts}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Storage account: $RESOURCE_NAME"
    
    # Get key and endpoints
    STORAGE_KEY=$(az storage account keys list --resource-group $RESOURCE_GROUP_NAME --account-name $RESOURCE_NAME --query "[0].value" -o tsv 2>/dev/null | tr -d '[:space:]')
    STORAGE_BLOB_ENDPOINT=$(az storage account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "primaryEndpoints.blob" -o tsv 2>/dev/null | tr -d '[:space:]')
    STORAGE_QUEUE_ENDPOINT=$(az storage account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "primaryEndpoints.queue" -o tsv 2>/dev/null | tr -d '[:space:]')
    STORAGE_ACCOUNT_ID=$(az storage account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "id" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    echo "AZURE_STORAGE_ACCOUNT_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
    
    if [ -n "$STORAGE_KEY" ]; then
      echo "AZURE_STORAGE_ACCOUNT_KEY=\"$STORAGE_KEY\"" >> $ENV_FILE
      echo "AZURE_STORAGE_BLOB_ENDPOINT=\"$STORAGE_BLOB_ENDPOINT\"" >> $ENV_FILE
      echo "AZURE_STORAGE_QUEUE_ENDPOINT=\"$STORAGE_QUEUE_ENDPOINT\"" >> $ENV_FILE
      echo "AZURE_STORAGE_ACCOUNT_ID=\"$STORAGE_ACCOUNT_ID\"" >> $ENV_FILE
      
      # Try to list containers - if fails, use default names
      if [ -n "$STORAGE_KEY" ]; then
        echo "Listing storage containers..."
        CONTAINERS=$(az storage container list --account-name $RESOURCE_NAME --account-key $STORAGE_KEY --query "[].{name:name}" -o tsv 2>/dev/null || echo "")
        
        # Look for specific containers from bicep
        DOCUMENT_CONTAINER=$(echo "$CONTAINERS" | grep -E "document-data|document_data" || echo "")
        JSON_CONTAINER=$(echo "$CONTAINERS" | grep -E "json-data|json_data" || echo "")
        PROCESSED_CONTAINER=$(echo "$CONTAINERS" | grep -E "processed" || echo "")
        
        if [ -n "$JSON_CONTAINER" ]; then
          echo "AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME=\"$JSON_CONTAINER\"" >> $ENV_FILE
        else
          echo "AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME=\"json-data\"" >> $ENV_FILE
        fi
        
        if [ -n "$DOCUMENT_CONTAINER" ]; then
          echo "AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME=\"$DOCUMENT_CONTAINER\"" >> $ENV_FILE
        else
          echo "AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME=\"document-data\"" >> $ENV_FILE
        fi
        
        if [ -n "$PROCESSED_CONTAINER" ]; then
          echo "AZURE_STORAGE_OUTPUT_CONTAINER_NAME=\"$PROCESSED_CONTAINER\"" >> $ENV_FILE
        else
          echo "AZURE_STORAGE_OUTPUT_CONTAINER_NAME=\"processed\"" >> $ENV_FILE
        fi
        
        # Try to get queues, use default if fails
        echo "Listing storage queues..."
        QUEUES=$(az storage queue list --account-name $RESOURCE_NAME --account-key $STORAGE_KEY --query "[].{name:name}" -o tsv 2>/dev/null || echo "")
        DOC_QUEUE=$(echo "$QUEUES" | grep -E "doc-process-queue|document-queue" || echo "")
        
        if [ -n "$DOC_QUEUE" ]; then
          echo "AZURE_STORAGE_QUEUE_NAME=\"$DOC_QUEUE\"" >> $ENV_FILE
        else
          echo "AZURE_STORAGE_QUEUE_NAME=\"doc-process-queue\"" >> $ENV_FILE
        fi
      else
        # Default values if can't access storage account
        echo "AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME=\"json-data\"" >> $ENV_FILE
        echo "AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME=\"document-data\"" >> $ENV_FILE
        echo "AZURE_STORAGE_OUTPUT_CONTAINER_NAME=\"processed\"" >> $ENV_FILE
        echo "AZURE_STORAGE_QUEUE_NAME=\"doc-process-queue\"" >> $ENV_FILE
      fi
    else
      echo "⚠️ Warning: Could not get key for Storage resource $RESOURCE_NAME"
      # Default values if can't access storage account
      echo "AZURE_STORAGE_ACCOUNT_KEY=\"\"" >> $ENV_FILE
      echo "AZURE_STORAGE_BLOB_ENDPOINT=\"\"" >> $ENV_FILE
      echo "AZURE_STORAGE_QUEUE_ENDPOINT=\"\"" >> $ENV_FILE
      echo "AZURE_STORAGE_ACCOUNT_ID=\"\"" >> $ENV_FILE
      echo "AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME=\"json-data\"" >> $ENV_FILE
      echo "AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME=\"document-data\"" >> $ENV_FILE
      echo "AZURE_STORAGE_OUTPUT_CONTAINER_NAME=\"processed\"" >> $ENV_FILE
      echo "AZURE_STORAGE_QUEUE_NAME=\"doc-process-queue\"" >> $ENV_FILE
    fi
  done
else
  echo "AZURE_STORAGE_ACCOUNT_NAME=\"\"" >> $ENV_FILE
  echo "AZURE_STORAGE_ACCOUNT_KEY=\"\"" >> $ENV_FILE
  echo "AZURE_STORAGE_BLOB_ENDPOINT=\"\"" >> $ENV_FILE
  echo "AZURE_STORAGE_QUEUE_ENDPOINT=\"\"" >> $ENV_FILE
  echo "AZURE_STORAGE_ACCOUNT_ID=\"\"" >> $ENV_FILE
  echo "AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME=\"json-data\"" >> $ENV_FILE
  echo "AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME=\"document-data\"" >> $ENV_FILE
  echo "AZURE_STORAGE_OUTPUT_CONTAINER_NAME=\"processed\"" >> $ENV_FILE
  echo "AZURE_STORAGE_QUEUE_NAME=\"doc-process-queue\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Azure AI Foundry section
echo "# Azure AI Foundry" >> $ENV_FILE
echo "FOUNDRY_PROJECT=\"\"" >> $ENV_FILE
echo "" >> $ENV_FILE

# Get Application Insights resource
echo "# Application Insights Resource" >> $ENV_FILE
appinsights_count=$(echo $app_insights | jq 'length')

if [ "$appinsights_count" -gt "0" ]; then
  for row in $(echo "${app_insights}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Application Insights: $RESOURCE_NAME"
    
    APP_INSIGHTS_CONN_STRING=$(az monitor app-insights component show --app $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "connectionString" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    if [ -n "$APP_INSIGHTS_CONN_STRING" ]; then
      echo "APP_INSIGHTS_CONN_STRING=\"$APP_INSIGHTS_CONN_STRING\"" >> $ENV_FILE
    else
      echo "⚠️ Warning: Could not get connection string for App Insights resource $RESOURCE_NAME"
      echo "APP_INSIGHTS_CONN_STRING=\"\"" >> $ENV_FILE
    fi
  done
else
  echo "APP_INSIGHTS_CONN_STRING=\"\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Get Container Apps and Container Registry
echo "# Azure Container Apps and Registry" >> $ENV_FILE
acr_count=$(echo $registries | jq 'length')

if [ "$acr_count" -gt "0" ]; then
  for row in $(echo "${registries}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Container Registry: $RESOURCE_NAME"
    
    # Enable admin to get credentials - ignore errors
    az acr update -n $RESOURCE_NAME --admin-enabled true 1>/dev/null 2>/dev/null || true
    
    ACR_LOGIN_SERVER=$(az acr show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "loginServer" -o tsv 2>/dev/null | tr -d '[:space:]')
    ACR_USER=$(az acr credential show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "username" -o tsv 2>/dev/null | tr -d '[:space:]')
    ACR_PASSWORD=$(az acr credential show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "passwords[0].value" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    echo "AZURE_ACR_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
    
    if [ -n "$ACR_LOGIN_SERVER" ]; then
      echo "AZURE_ACR_SERVER=\"$ACR_LOGIN_SERVER\"" >> $ENV_FILE
    else
      echo "AZURE_ACR_SERVER=\"\"" >> $ENV_FILE
    fi
    
    if [ -n "$ACR_USER" ] && [ -n "$ACR_PASSWORD" ]; then
      echo "AZURE_ACR_USERNAME=\"$ACR_USER\"" >> $ENV_FILE
      echo "AZURE_ACR_PASSWORD=\"$ACR_PASSWORD\"" >> $ENV_FILE
    else
      echo "⚠️ Warning: Could not get credentials for ACR resource $RESOURCE_NAME"
      echo "AZURE_ACR_USERNAME=\"\"" >> $ENV_FILE
      echo "AZURE_ACR_PASSWORD=\"\"" >> $ENV_FILE
    fi
  done
else
  echo "AZURE_ACR_NAME=\"\"" >> $ENV_FILE
  echo "AZURE_ACR_SERVER=\"\"" >> $ENV_FILE
  echo "AZURE_ACR_USERNAME=\"\"" >> $ENV_FILE
  echo "AZURE_ACR_PASSWORD=\"\"" >> $ENV_FILE
fi

# Get Container Apps Environment
aca_env_count=$(echo $container_apps_env | jq 'length')

if [ "$aca_env_count" -gt "0" ]; then
  for row in $(echo "${container_apps_env}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Container Apps Environment: $RESOURCE_NAME"
    
    echo "AZURE_ACA_ENVIRONMENT=\"$RESOURCE_NAME\"" >> $ENV_FILE
  done
else
  echo "AZURE_ACA_ENVIRONMENT=\"\"" >> $ENV_FILE
fi

# Get Container Apps
aca_count=$(echo $container_apps | jq 'length')

if [ "$aca_count" -gt "0" ]; then
  for row in $(echo "${container_apps}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Container App: $RESOURCE_NAME"
    
    ACA_ENDPOINT=$(az containerapp show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    echo "AZURE_CONTAINER_APP_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
    if [ -n "$ACA_ENDPOINT" ]; then
      echo "AZURE_CONTAINER_APP_ENDPOINT=\"$ACA_ENDPOINT\"" >> $ENV_FILE
    else
      echo "AZURE_CONTAINER_APP_ENDPOINT=\"\"" >> $ENV_FILE
    fi
  done
else
  echo "AZURE_CONTAINER_APP_NAME=\"\"" >> $ENV_FILE
  echo "AZURE_CONTAINER_APP_ENDPOINT=\"\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Get Cosmos DB resources
echo "# Cosmos DB Settings" >> $ENV_FILE
cosmos_count=$(echo $cosmosdb_resources | jq 'length')

if [ "$cosmos_count" -gt "0" ]; then
  for row in $(echo "${cosmosdb_resources}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Cosmos DB Account: $RESOURCE_NAME"
    
    COSMOS_KEY=$(az cosmosdb keys list --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --type keys --query "primaryMasterKey" -o tsv 2>/dev/null | tr -d '[:space:]')
    COSMOS_ENDPOINT=$(az cosmosdb show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "documentEndpoint" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    echo "COSMOS_URI=\"$COSMOS_ENDPOINT\"" >> $ENV_FILE
    
    if [ -n "$COSMOS_KEY" ]; then
      echo "COSMOS_KEY=\"$COSMOS_KEY\"" >> $ENV_FILE
      
      # Try to get database info - this might fail if permissions aren't right
      echo "Listing Cosmos databases..."
      
      # Use the deprecated command for compatibility but add error handling
      COSMOS_DBS=$(az cosmosdb database list --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "[].{name:name}" -o tsv 2>/dev/null || echo "")
      
      if [ -n "$COSMOS_DBS" ]; then
        # Use the first database or the one matching "proc-docs" if exists
        PROC_DOCS_DB=$(echo "$COSMOS_DBS" | grep -E "proc-docs" || echo "")
        if [ -n "$PROC_DOCS_DB" ]; then
          COSMOS_DB="$PROC_DOCS_DB"
        else
          COSMOS_DB=$(echo "$COSMOS_DBS" | head -n 1)
        fi
        
        # If returned as "None", set to default "proc-docs"
        if [ "$COSMOS_DB" = "None" ]; then
          COSMOS_DB="proc-docs"
        fi
        
        # If returned as "None", set to default "proc-docs"
        if [ "$COSMOS_DB" = "" ]; then
          COSMOS_DB="proc-docs"
        fi


        echo "COSMOS_DB_NAME=\"$COSMOS_DB\"" >> $ENV_FILE
        
        # Get containers in the database
        echo "Listing Cosmos containers..."
        COSMOS_CONTAINERS=$(az cosmosdb sql container list --account-name $RESOURCE_NAME --database-name $COSMOS_DB --resource-group $RESOURCE_GROUP_NAME --query "[].{name:name, partitionKey:partitionKey.paths[0]}" -o json 2>/dev/null || echo "[]")
        
        if [ "$(echo "$COSMOS_CONTAINERS" | jq 'length')" -gt "0" ]; then
          for container_row in $(echo "${COSMOS_CONTAINERS}" | jq -r '.[] | @base64'); do
            _container_jq() {
              echo ${container_row} | base64 --decode | jq -r ${1} 2>/dev/null
            }
            
            CONTAINER_NAME=$(_container_jq '.name')
            PARTITION_KEY=$(_container_jq '.partitionKey')
            
            # Strip the leading '/' from the partition key
            if [ -n "$PARTITION_KEY" ]; then
              PARTITION_KEY_NAME=${PARTITION_KEY:1}
            else
              PARTITION_KEY_NAME="categoryId"
            fi
            
            echo "COSMOS_CONTAINER_NAME=\"$CONTAINER_NAME\"" >> $ENV_FILE
            echo "COSMOS_CATEGORYID=\"$PARTITION_KEY_NAME\"" >> $ENV_FILE
            echo "COSMOS_CATEGORYID_VALUE=\"documents\"" >> $ENV_FILE
            echo "COSMOS_LOG_CONTAINER=\"logs\"" >> $ENV_FILE
            break # Just use the first container
          done
        else
          # Use default values if no containers found
          echo "COSMOS_CONTAINER_NAME=\"documents\"" >> $ENV_FILE
          echo "COSMOS_CATEGORYID=\"categoryId\"" >> $ENV_FILE
          echo "COSMOS_CATEGORYID_VALUE=\"documents\"" >> $ENV_FILE
          echo "COSMOS_LOG_CONTAINER=\"logs\"" >> $ENV_FILE
        fi
      else
        # Use default values if no database found
        echo "COSMOS_DB_NAME=\"proc-docs\"" >> $ENV_FILE
        echo "COSMOS_CONTAINER_NAME=\"documents\"" >> $ENV_FILE
        echo "COSMOS_CATEGORYID=\"categoryId\"" >> $ENV_FILE
        echo "COSMOS_CATEGORYID_VALUE=\"documents\"" >> $ENV_FILE
        echo "COSMOS_LOG_CONTAINER=\"logs\"" >> $ENV_FILE
      fi
    else
      echo "⚠️ Warning: Could not get key for Cosmos DB resource $RESOURCE_NAME"
      echo "COSMOS_KEY=\"\"" >> $ENV_FILE
      # Add default values
      echo "COSMOS_DB_NAME=\"proc-docs\"" >> $ENV_FILE
      echo "COSMOS_CONTAINER_NAME=\"documents\"" >> $ENV_FILE
      echo "COSMOS_CATEGORYID=\"categoryId\"" >> $ENV_FILE
      echo "COSMOS_CATEGORYID_VALUE=\"documents\"" >> $ENV_FILE
      echo "COSMOS_LOG_CONTAINER=\"logs\"" >> $ENV_FILE
    fi
  done
else
  echo "COSMOS_URI=\"\"" >> $ENV_FILE
  echo "COSMOS_KEY=\"\"" >> $ENV_FILE
  echo "COSMOS_DB_NAME=\"proc-docs\"" >> $ENV_FILE
  echo "COSMOS_CONTAINER_NAME=\"documents\"" >> $ENV_FILE
  echo "COSMOS_CATEGORYID=\"categoryId\"" >> $ENV_FILE
  echo "COSMOS_CATEGORYID_VALUE=\"documents\"" >> $ENV_FILE
  echo "COSMOS_LOG_CONTAINER=\"logs\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Get Service Bus resources
echo "# Service Bus Settings" >> $ENV_FILE
servicebus_count=$(echo $servicebus_namespaces | jq 'length')

if [ "$servicebus_count" -gt "0" ]; then
  for row in $(echo "${servicebus_namespaces}" | jq -r '.[] | @base64'); do
    _jq() {
      echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }
    
    RESOURCE_NAME=$(_jq '.Name')
    echo "Processing Service Bus Namespace: $RESOURCE_NAME"
    
    CONN_STRING=$(az servicebus namespace authorization-rule keys list --resource-group $RESOURCE_GROUP_NAME --namespace-name $RESOURCE_NAME --name RootManageSharedAccessKey --query "primaryConnectionString" -o tsv 2>/dev/null | tr -d '[:space:]')
    
    echo "SERVICE_BUS_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
    if [ -n "$CONN_STRING" ]; then
      echo "SERVICE_BUS_CONNECTION_STRING=\"$CONN_STRING\"" >> $ENV_FILE
    else
      echo "⚠️ Warning: Could not get connection string for Service Bus resource $RESOURCE_NAME"
      echo "SERVICE_BUS_CONNECTION_STRING=\"\"" >> $ENV_FILE
    fi
    
    # Get queues
    echo "Listing Service Bus queues..."
    SB_QUEUES=$(az servicebus queue list --resource-group $RESOURCE_GROUP_NAME --namespace-name $RESOURCE_NAME --query "[].{name:name}" -o tsv 2>/dev/null || echo "")
    
    if [ -n "$SB_QUEUES" ]; then
      # Look for the document processing queue or use the first one
      DOC_QUEUE=$(echo "$SB_QUEUES" | grep -E "document-processing-queue" || echo "")
      if [ -n "$DOC_QUEUE" ]; then
        echo "SERVICE_BUS_QUEUE_NAME=\"$DOC_QUEUE\"" >> $ENV_FILE
      else
        FIRST_QUEUE=$(echo "$SB_QUEUES" | head -n 1)
        echo "SERVICE_BUS_QUEUE_NAME=\"$FIRST_QUEUE\"" >> $ENV_FILE
      fi
    else
      echo "SERVICE_BUS_QUEUE_NAME=\"document-processing-queue\"" >> $ENV_FILE
    fi
  done
else
  echo "SERVICE_BUS_NAME=\"\"" >> $ENV_FILE
  echo "SERVICE_BUS_CONNECTION_STRING=\"\"" >> $ENV_FILE
  echo "SERVICE_BUS_QUEUE_NAME=\"document-processing-queue\"" >> $ENV_FILE
fi

echo "" >> $ENV_FILE

# Get User Assigned Managed Identity
echo "# User-Assigned Managed Identity" >> $ENV_FILE
USER_IDENTITIES=$(az identity list --resource-group $RESOURCE_GROUP_NAME --query "[].{name:name, clientId:clientId}" -o json 2>/dev/null || echo "[]")

if [ "$(echo "$USER_IDENTITIES" | jq 'length')" -gt "0" ]; then
  # Just use the first one if multiple exist
  CLIENT_ID=$(echo "$USER_IDENTITIES" | jq -r '.[0].clientId' 2>/dev/null)
  if [ -n "$CLIENT_ID" ]; then
    echo "AZURE_CLIENT_ID=\"$CLIENT_ID\"" >> $ENV_FILE
  else
    echo "AZURE_CLIENT_ID=\"\"" >> $ENV_FILE
  fi
else
  echo "AZURE_CLIENT_ID=\"\"" >> $ENV_FILE
fi

# Clean up any carriage returns or trailing whitespace in the entire file
if [ -f "$ENV_FILE" ]; then
  # Create a temporary file
  TMP_FILE="${ENV_FILE}.tmp"
  
  # Process the file to clean up carriage returns and trailing whitespace
  cat "$ENV_FILE" | tr -d '\r' | sed 's/[[:space:]]*$//' > "$TMP_FILE"
  
  # Replace the original with the cleaned version
  mv "$TMP_FILE" "$ENV_FILE"
  
  echo "Cleaned up carriage returns and trailing whitespace in $ENV_FILE"
fi

echo "Environment file generation complete. File saved to: $ENV_FILE"