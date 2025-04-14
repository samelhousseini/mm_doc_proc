#!/bin/bash

# Check if the subscription ID, resource group name, and optionally the save path are provided as command-line arguments
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <subscription-id> <resource-group-name> [path-to-save-env-file]"
  exit 1
fi

# Set the subscription ID, resource group name, and optional path from the CLI arguments
SUBSCRIPTION_ID="$1"
RESOURCE_GROUP_NAME="$2"
SAVE_PATH="${3:-.}"  # Default to current directory if no path is provided

# Set the Azure subscription and default resource group
az account set --subscription $SUBSCRIPTION_ID
az configure --default group=$RESOURCE_GROUP_NAME

# Dynamically create the .env file based on the resource group name and save it to the specified path
ENV_FILE="${SAVE_PATH}/.env.RG_${RESOURCE_GROUP_NAME}"
> "$ENV_FILE"  # Clear the file if it exists

echo "Saving .env file to: $ENV_FILE"

# Initialize counters for each resource type
STORAGE_COUNTER=0
OPENAI_COUNTER=0
LANGUAGE_COUNTER=0
VISION_COUNTER=0
SPEECH_COUNTER=0
TRANSLATOR_COUNTER=0
DOCUMENT_COUNTER=0
SEARCH_COUNTER=0
CONTENT_COUNTER=0
WEB_APP_COUNTER=0
COSMOS_COUNTER=0
AML_COUNTER=0
ACR_COUNTER=0
ACA_COUNTER=0
ACA_ENV_COUNTER=0
APP_INSIGHTS_COUNTER=0
KEY_VAULT_COUNTER=0
VNET_COUNTER=0
PRIVATE_LINK_COUNTER=0

# Get all resources in the specified resource group
resources=$(az resource list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "General Resources: ${resources}"

# Get Cognitive Services resources with their kinds
cognitive_services=$(az cognitiveservices account list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Cognitive Services: ${cognitive_services}"

# Get ACR registries in the specified resource group
registries=$(az acr list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Registries: ${registries}"

# Get Azure Container Apps in the specified resource group
container_apps=$(az containerapp list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Container Apps: ${container_apps}"

# Get Azure Container Apps Environments in the specified resource group
container_apps_env=$(az containerapp env list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Container Apps Envs: ${container_apps_env}"

# Get Azure Storage Accounts in the specified resource group
storage_accounts=$(az storage account list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Storage Accounts: ${storage_accounts}"

# Get Azure Machine Learning resources in the specified resource group
aml_workspaces_raw=$(az ml workspace list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
aml_workspaces=$(echo "${aml_workspaces_raw}" | jq '.[] |= . + {"Type": "Microsoft.MachineLearningServices/workspaces"}')
echo "AML: ${aml_workspaces}"

# Get Cosmos DB resources in the specified resource group
cosmosdb_resources=$(az cosmosdb list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Cosmos DB: ${cosmosdb_resources}"

# Get Azure Search services in the specified resource group
ai_search_services=$(az search service list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "AI Search Services: ${ai_search_services}"

# Get Azure Web Apps in the specified resource group
web_apps=$(az webapp list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Web Apps: ${web_apps}"

# Get Application Insights resources in the specified resource group
app_insights=$(az monitor app-insights component list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Application Insights: ${app_insights}"

# Get Key Vaults in the specified resource group
key_vaults=$(az keyvault list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Key Vaults: ${key_vaults}"

# Get Virtual Networks in the specified resource group
vnets=$(az network vnet list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Virtual Networks: ${vnets}"

# Get Private Links in the specified resource group
private_links=$(az network private-link-service list --resource-group $RESOURCE_GROUP_NAME --query "[].{Name:name, Type:type, Kind:kind}" -o json)
echo "Private Links: ${private_links}"

# Combine all resources
combined_resources=$(echo $resources $cognitive_services $registries $container_apps $container_apps_env $storage_accounts $aml_workspaces $cosmosdb_resources $ai_search_services $web_apps $app_insights $key_vaults $vnets $private_links | jq -s 'add')

# Iterate over each resource and gather relevant information based on resource type and kind
for row in $(echo "${combined_resources}" | jq -r '.[] | @base64'); do
    _jq() {
        echo ${row} | base64 --decode | jq -r ${1} 2>/dev/null
    }

    echo "Decoded row: $(echo ${row} | base64 --decode)"  # Debugging line

    RESOURCE_NAME=$(_jq '.Name')
    RESOURCE_TYPE=$(_jq '.Type')
    RESOURCE_KIND=$(_jq '.Kind')

    echo "Processing $RESOURCE_NAME of type $RESOURCE_TYPE and kind $RESOURCE_KIND..."

    case $RESOURCE_TYPE in
        "Microsoft.Storage/storageAccounts")
            STORAGE_KEY=$(az storage account keys list --resource-group $RESOURCE_GROUP_NAME --account-name $RESOURCE_NAME --query "[0].value" -o tsv | tr -d '[:space:]')
            STORAGE_BLOB_ENDPOINT=$(az storage account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "primaryEndpoints.blob" -o tsv | tr -d '[:space:]')
            BLOB_CONN_STR=$(az storage account show-connection-string --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "connectionString" -o tsv | tr -d '[:space:]')
            if [ $STORAGE_COUNTER -eq 0 ]; then
                echo "STORAGE_BLOB_ENDPOINT=\"$STORAGE_BLOB_ENDPOINT\"" >> $ENV_FILE
                echo "STORAGE_ACCOUNT_KEY=\"$STORAGE_KEY\"" >> $ENV_FILE
                echo "BLOB_CONN_STR=\"$BLOB_CONN_STR\"" >> $ENV_FILE
            else
                echo "STORAGE_BLOB_ENDPOINT_${STORAGE_COUNTER}=\"$STORAGE_BLOB_ENDPOINT\"" >> $ENV_FILE
                echo "STORAGE_ACCOUNT_KEY_${STORAGE_COUNTER}=\"$STORAGE_KEY\"" >> $ENV_FILE
                echo "BLOB_CONN_STR_${STORAGE_COUNTER}=\"$BLOB_CONN_STR\"" >> $ENV_FILE
            fi
            STORAGE_COUNTER=$((STORAGE_COUNTER + 1))
            ;;
        "Microsoft.CognitiveServices/accounts")
            COGNITIVE_ENDPOINT=$(az cognitiveservices account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "properties.endpoint" -o tsv | tr -d '[:space:]')
            COGNITIVE_KEY=$(az cognitiveservices account keys list --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "key1" -o tsv | tr -d '[:space:]')

            case $RESOURCE_KIND in
                "OpenAI")
                    if [ $OPENAI_COUNTER -eq 0 ]; then
                        echo "OPENAI_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "OPENAI_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "OPENAI_ENDPOINT_${OPENAI_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "OPENAI_KEY_${OPENAI_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    OPENAI_COUNTER=$((OPENAI_COUNTER + 1))
                    ;;
                "Language")
                    if [ $LANGUAGE_COUNTER -eq 0 ]; then
                        echo "LANGUAGE_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "LANGUAGE_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "LANGUAGE_ENDPOINT_${LANGUAGE_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "LANGUAGE_KEY_${LANGUAGE_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    LANGUAGE_COUNTER=$((LANGUAGE_COUNTER + 1))
                    ;;
                "ComputerVision")
                    if [ $VISION_COUNTER -eq 0 ]; then
                        echo "VISION_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "VISION_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "VISION_ENDPOINT_${VISION_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "VISION_KEY_${VISION_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    VISION_COUNTER=$((VISION_COUNTER + 1))
                    ;;
                "SpeechServices")
                    if [ $SPEECH_COUNTER -eq 0 ]; then
                        echo "SPEECH_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "SPEECH_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "SPEECH_ENDPOINT_${SPEECH_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "SPEECH_KEY_${SPEECH_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    SPEECH_COUNTER=$((SPEECH_COUNTER + 1))
                    ;;
                "TextTranslation")
                    if [ $TRANSLATOR_COUNTER -eq 0 ]; then
                        echo "TRANSLATOR_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "TRANSLATOR_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "TRANSLATOR_ENDPOINT_${TRANSLATOR_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "TRANSLATOR_KEY_${TRANSLATOR_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    TRANSLATOR_COUNTER=$((TRANSLATOR_COUNTER + 1))
                    ;;
                "FormRecognizer" | "DocumentIntelligence")
                    if [ $DOCUMENT_COUNTER -eq 0 ]; then
                        echo "DOCUMENT_INTELLIGENCE_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "DOCUMENT_INTELLIGENCE_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "DOCUMENT_INTELLIGENCE_ENDPOINT_${DOCUMENT_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "DOCUMENT_INTELLIGENCE_KEY_${DOCUMENT_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    DOCUMENT_COUNTER=$((DOCUMENT_COUNTER + 1))
                    ;;
                "AnomalyDetector")
                    if [ $ANOMALY_COUNTER -eq 0 ]; then
                        echo "ANOMALY_DETECTOR_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "ANOMALY_DETECTOR_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "ANOMALY_DETECTOR_ENDPOINT_${ANOMALY_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "ANOMALY_DETECTOR_KEY_${ANOMALY_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    ANOMALY_COUNTER=$((ANOMALY_COUNTER + 1))
                    ;;
                "ContentModerator" | "ContentSafety")
                    if [ $CONTENT_COUNTER -eq 0 ]; then
                        echo "CONTENT_MODERATOR_ENDPOINT=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "CONTENT_MODERATOR_KEY=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    else
                        echo "CONTENT_MODERATOR_ENDPOINT_${CONTENT_COUNTER}=\"$COGNITIVE_ENDPOINT\"" >> $ENV_FILE
                        echo "CONTENT_MODERATOR_KEY_${CONTENT_COUNTER}=\"$COGNITIVE_KEY\"" >> $ENV_FILE
                    fi
                    CONTENT_COUNTER=$((CONTENT_COUNTER + 1))
                    ;;
                *)
                    echo "Unknown Cognitive Services kind: $RESOURCE_KIND"
                    ;;
            esac
            ;;
        "Microsoft.Web/sites")
            WEB_APP_URL=$(az webapp show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "defaultHostName" -o tsv | tr -d '[:space:]')
            if [ $WEB_APP_COUNTER -eq 0 ]; then
                echo "WEB_APP_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "WEB_APP_URL=\"$WEB_APP_URL\"" >> $ENV_FILE
            else
                echo "WEB_APP_NAME_${WEB_APP_COUNTER}=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "WEB_APP_URL_${WEB_APP_COUNTER}=\"$WEB_APP_URL\"" >> $ENV_FILE
            fi
            WEB_APP_COUNTER=$((WEB_APP_COUNTER + 1))
            ;;
        "Microsoft.DocumentDB/databaseAccounts")
            COSMOS_KEY=$(az cosmosdb keys list --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --type keys --query "primaryMasterKey" -o tsv | tr -d '[:space:]')
            COSMOS_ENDPOINT=$(az cosmosdb show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "documentEndpoint" -o tsv | tr -d '[:space:]')
            if [ $COSMOS_COUNTER -eq 0 ]; then
                echo "COSMOS_ENDPOINT=\"$COSMOS_ENDPOINT\"" >> $ENV_FILE
                echo "COSMOS_KEY=\"$COSMOS_KEY\"" >> $ENV_FILE
            else
                echo "COSMOS_ENDPOINT_${COSMOS_COUNTER}=\"$COSMOS_ENDPOINT\"" >> $ENV_FILE
                echo "COSMOS_KEY_${COSMOS_COUNTER}=\"$COSMOS_KEY\"" >> $ENV_FILE
            fi
            COSMOS_COUNTER=$((COSMOS_COUNTER + 1))
            ;;
        "Microsoft.Search/searchServices")
            SEARCH_KEY=$(az search admin-key show --resource-group $RESOURCE_GROUP_NAME --service-name $RESOURCE_NAME --query "primaryKey" -o tsv | tr -d '[:space:]')
            SEARCH_ENDPOINT="https://${RESOURCE_NAME}.search.windows.net"
            if [ $SEARCH_COUNTER -eq 0 ]; then
                echo "SEARCH_ENDPOINT=\"$SEARCH_ENDPOINT\"" >> $ENV_FILE
                echo "SEARCH_KEY=\"$SEARCH_KEY\"" >> $ENV_FILE
            else
                echo "SEARCH_ENDPOINT_${SEARCH_COUNTER}=\"$SEARCH_ENDPOINT\"" >> $ENV_FILE
                echo "SEARCH_KEY_${SEARCH_COUNTER}=\"$SEARCH_KEY\"" >> $ENV_FILE
            fi
            SEARCH_COUNTER=$((SEARCH_COUNTER + 1))
            ;;
        "Microsoft.MachineLearningServices/workspaces")
            AML_WORKSPACE_NAME=$RESOURCE_NAME
            AML_ENDPOINT=$(az ml workspace show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "mlflow_tracking_uri" -o tsv | tr -d '[:space:]')
            AML_KEY=$(az ml workspace keys list --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "userStorageKey" -o tsv | tr -d '[:space:]')
            if [ $AML_COUNTER -eq 0 ]; then
                echo "AML_WORKSPACE_NAME=\"$AML_WORKSPACE_NAME\"" >> $ENV_FILE
                echo "AML_ENDPOINT=\"$AML_ENDPOINT\"" >> $ENV_FILE
                echo "AML_KEY=\"$AML_KEY\"" >> $ENV_FILE
            else
                echo "AML_WORKSPACE_NAME_${AML_COUNTER}=\"$AML_WORKSPACE_NAME\"" >> $ENV_FILE
                echo "AML_ENDPOINT_${AML_COUNTER}=\"$AML_ENDPOINT\"" >> $ENV_FILE
                echo "AML_KEY_${AML_COUNTER}=\"$AML_KEY\"" >> $ENV_FILE
            fi
            AML_COUNTER=$((AML_COUNTER + 1))
            ;;
        "Microsoft.App/containerApps")
            ACA_ENDPOINT=$(az containerapp show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "properties.configuration.ingress.fqdn" -o tsv | tr -d '[:space:]')
            if [ $ACA_COUNTER -eq 0 ]; then
                echo "AZURE_CONTAINER_APP_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_APP_ENDPOINT=\"$ACA_ENDPOINT\"" >> $ENV_FILE
            else
                echo "AZURE_CONTAINER_APP_NAME_${ACA_COUNTER}=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_APP_ENDPOINT_${ACA_COUNTER}=\"$ACA_ENDPOINT\"" >> $ENV_FILE
            fi
            ACA_COUNTER=$((ACA_COUNTER + 1))
            ;;
        "Microsoft.App/managedEnvironments")
            ACA_ENV_NAME=$RESOURCE_NAME
            if [ $ACA_ENV_COUNTER -eq 0 ]; then
                echo "AZURE_CONTAINER_APP_ENVIRONMENT=\"$ACA_ENV_NAME\"" >> $ENV_FILE
            else
                echo "AZURE_CONTAINER_APP_ENVIRONMENT_${ACA_ENV_COUNTER}=\"$ACA_ENV_NAME\"" >> $ENV_FILE
            fi
            ACA_ENV_COUNTER=$((ACA_ENV_COUNTER + 1))
            ;;
        "Microsoft.ContainerRegistry/registries")
            az acr update -n $RESOURCE_NAME --admin-enabled true >/dev/null
            ACR_LOGIN_SERVER=$(az acr show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "loginServer" -o tsv | tr -d '[:space:]')
            ACR_USER=$(az acr credential show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "username" -o tsv | tr -d '[:space:]')
            ACR_PASSWORD=$(az acr credential show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "passwords[0].value" -o tsv | tr -d '[:space:]')

            if [ $ACR_COUNTER -eq 0 ]; then
                echo "AZURE_CONTAINER_REGISTRY_NAME=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_SERVER=\"$ACR_LOGIN_SERVER\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_USER=\"$ACR_USER\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_PASSWORD=\"$ACR_PASSWORD\"" >> $ENV_FILE
            else
                echo "AZURE_CONTAINER_REGISTRY_NAME_${ACR_COUNTER}=\"$RESOURCE_NAME\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_SERVER_${ACR_COUNTER}=\"$ACR_LOGIN_SERVER\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_USER_${ACR_COUNTER}=\"$ACR_USER\"" >> $ENV_FILE
                echo "AZURE_CONTAINER_REGISTRY_PASSWORD_${ACR_COUNTER}=\"$ACR_PASSWORD\"" >> $ENV_FILE
            fi
            ACR_COUNTER=$((ACR_COUNTER + 1))
            ;;
        "Microsoft.Insights/components")
            APP_INSIGHTS_KEY=$(az monitor app-insights component show --app $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "connectionString" -o tsv | tr -d '[:space:]')
            if [ $APP_INSIGHTS_COUNTER -eq 0 ]; then
                echo "APPLICATION_INSIGHTS_CONNECTION_STRING=\"$APP_INSIGHTS_KEY\"" >> $ENV_FILE
            else
                echo "APPLICATION_INSIGHTS_CONNECTION_STRING_${APP_INSIGHTS_COUNTER}=\"$APP_INSIGHTS_KEY\"" >> $ENV_FILE
            fi
            APP_INSIGHTS_COUNTER=$((APP_INSIGHTS_COUNTER + 1))
            ;;
        "Microsoft.KeyVault/vaults")
            KEY_VAULT_URI=$(az keyvault show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "properties.vaultUri" -o tsv | tr -d '[:space:]')
            if [ $KEY_VAULT_COUNTER -eq 0 ]; then
                echo "KEY_VAULT_URI=\"$KEY_VAULT_URI\"" >> $ENV_FILE
            else
                echo "KEY_VAULT_URI_${KEY_VAULT_COUNTER}=\"$KEY_VAULT_URI\"" >> $ENV_FILE
            fi
            KEY_VAULT_COUNTER=$((KEY_VAULT_COUNTER + 1))
            ;;
        "Microsoft.Network/virtualNetworks")
            VNET_ID=$(az network vnet show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "id" -o tsv | tr -d '[:space:]')
            if [ $VNET_COUNTER -eq 0 ]; then
                echo "VIRTUAL_NETWORK_ID=\"$VNET_ID\"" >> $ENV_FILE
            else
                echo "VIRTUAL_NETWORK_ID_${VNET_COUNTER}=\"$VNET_ID\"" >> $ENV_FILE
            fi
            VNET_COUNTER=$((VNET_COUNTER + 1))
            ;;
        "Microsoft.Network/privateLinkServices")
            PRIVATE_LINK_ID=$(az network private-link-service show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP_NAME --query "id" -o tsv | tr -d '[:space:]')
            if [ $PRIVATE_LINK_COUNTER -eq 0 ]; then
                echo "PRIVATE_LINK_SERVICE_ID=\"$PRIVATE_LINK_ID\"" >> $ENV_FILE
            else
                echo "PRIVATE_LINK_SERVICE_ID_${PRIVATE_LINK_COUNTER}=\"$PRIVATE_LINK_ID\"" >> $ENV_FILE
            fi
            PRIVATE_LINK_COUNTER=$((PRIVATE_LINK_COUNTER + 1))
            ;;
        *)
            echo "No specific action for resource type: $RESOURCE_TYPE"
            ;;
    esac

    echo "Finished processing $RESOURCE_NAME"
    echo "---------------------------------"
done

echo "All resources processed. Endpoints and keys have been written to $ENV_FILE"
