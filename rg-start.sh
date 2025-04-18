#!/bin/bash

# rg-start.sh
# Master script to configure Azure resources for the document processing solution
# This script orchestrates the execution of other configuration scripts

# Default values
RESOURCE_GROUP=""
STORAGE_ACCOUNT=""
COSMOS_ACCOUNT=""
PRINCIPAL_ID=""
GET_BICEP_CREDS=false
SUBSCRIPTION_ID=""

# Display help information
show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -g, --resource-group     Resource group name (required)"
    echo "  -s, --storage-account    Storage account name (required)"
    echo "  -c, --cosmos-account     Cosmos DB account name (required)"
    echo "  -p, --principal-id       Principal ID (user object ID) for role assignments (optional, will use logged-in user if not specified)"
    echo "  -i, --subscription-id    Azure subscription ID (optional, current subscription used if not specified)"
    echo "  -b, --get-bicep-creds    Get Bicep deployment credentials (optional)"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 -g myResourceGroup -s myStorageAccount -c myCosmosAccount -i yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -g|--resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        -s|--storage-account)
            STORAGE_ACCOUNT="$2"
            shift 2
            ;;
        -c|--cosmos-account)
            COSMOS_ACCOUNT="$2"
            shift 2
            ;;
        -p|--principal-id)
            PRINCIPAL_ID="$2"
            shift 2
            ;;
        -i|--subscription-id)
            SUBSCRIPTION_ID="$2"
            shift 2
            ;;
        -b|--get-bicep-creds)
            GET_BICEP_CREDS=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown parameter: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check required parameters
if [[ -z "$RESOURCE_GROUP" ]]; then
    echo "Error: Resource group name is required (-g or --resource-group)"
    show_help
    exit 1
fi

if [[ -z "$STORAGE_ACCOUNT" ]]; then
    echo "Error: Storage account name is required (-s or --storage-account)"
    show_help
    exit 1
fi

if [[ -z "$COSMOS_ACCOUNT" ]]; then
    echo "Error: Cosmos DB account name is required (-c or --cosmos-account)"
    show_help
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Ensure user is logged in to Azure
echo "Checking Azure login status..."
ACCOUNT=$(az account show --query name -o tsv 2>/dev/null)
if [[ -z "$ACCOUNT" ]]; then
    echo "You are not logged in to Azure. Please run 'az login' first."
    exit 1
fi
echo "Logged in as: $ACCOUNT"

# Get the principal ID of the logged-in user if not provided
if [[ -z "$PRINCIPAL_ID" ]]; then
    echo "No principal ID provided, detecting current user's principal ID..."
    # Get the object ID of the logged-in user
    PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null)
    
    if [[ -z "$PRINCIPAL_ID" ]]; then
        echo "Error: Failed to detect current user's principal ID. Please provide it using the -p or --principal-id option."
        exit 1
    fi
    echo "Using current user's principal ID: $PRINCIPAL_ID"
fi

# Get subscription ID if not provided
if [[ -z "$SUBSCRIPTION_ID" ]]; then
    echo "No subscription ID provided, using current subscription..."
    SUBSCRIPTION_ID=$(az account show --query id -o tsv)
    if [[ -z "$SUBSCRIPTION_ID" ]]; then
        echo "Error: Failed to get current subscription ID."
        exit 1
    fi
    echo "Using subscription ID: $SUBSCRIPTION_ID"
fi

# Set the subscription context
echo "Setting subscription context to ID: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"
if [[ $? -ne 0 ]]; then
    echo "Error: Failed to set subscription context to ID: $SUBSCRIPTION_ID"
    exit 1
fi

# Step 1: Configure storage account access
echo "======================================"
echo "CONFIGURING STORAGE ACCOUNT ACCESS"
echo "======================================"
STORAGE_SCRIPT="$SCRIPT_DIR/storage/shells/configure_storage_access.sh"

if [[ -f "$STORAGE_SCRIPT" ]]; then
    echo "Running storage access configuration script..."
    bash "$STORAGE_SCRIPT" \
        --resource-group "$RESOURCE_GROUP" \
        --storage-account "$STORAGE_ACCOUNT" \
        --principal-id "$PRINCIPAL_ID" \
        --network-action "Allow" \
        --subscription-id "$SUBSCRIPTION_ID"
    
    if [[ $? -ne 0 ]]; then
        echo "Warning: Storage access configuration failed or completed with warnings."
    else
        echo "Storage access configuration completed successfully."
    fi
else
    echo "Error: Storage configuration script not found at $STORAGE_SCRIPT"
    exit 1
fi

# Step 2: Configure CosmosDB access
echo "======================================"
echo "CONFIGURING COSMOSDB ACCESS"
echo "======================================"
COSMOS_PUBLIC_SCRIPT="$SCRIPT_DIR/database/shells/cosmos-resetting-public-network.sh"
COSMOS_ROLE_SCRIPT="$SCRIPT_DIR/database/shells/custom-role.sh"

# Make CosmosDB network access public
if [[ -f "$COSMOS_PUBLIC_SCRIPT" ]]; then
    echo "Making CosmosDB network access public..."
    bash "$COSMOS_PUBLIC_SCRIPT" \
        --resource-group "$RESOURCE_GROUP" \
        --account-name "$COSMOS_ACCOUNT" \
        --subscription-id "$SUBSCRIPTION_ID"
    
    if [[ $? -ne 0 ]]; then
        echo "Warning: CosmosDB network configuration failed or completed with warnings."
    else
        echo "CosmosDB network configuration completed successfully."
    fi
else
    echo "Error: CosmosDB network configuration script not found at $COSMOS_PUBLIC_SCRIPT"
    exit 1
fi

# Create and assign custom role for CosmosDB
if [[ -f "$COSMOS_ROLE_SCRIPT" ]]; then
    echo "Configuring CosmosDB custom role and permissions..."
    bash "$COSMOS_ROLE_SCRIPT" \
        --resource-group "$RESOURCE_GROUP" \
        --account-name "$COSMOS_ACCOUNT" \
        --principal-id "$PRINCIPAL_ID" \
        --role-name "Azure Cosmos DB for NoSQL Data Plane Owner Custom Role" \
        --auto-assign \
        --subscription-id "$SUBSCRIPTION_ID"
    
    if [[ $? -ne 0 ]]; then
        echo "Warning: CosmosDB role assignment failed or completed with warnings."
    else
        echo "CosmosDB role assignment completed successfully."
    fi
else
    echo "Error: CosmosDB role script not found at $COSMOS_ROLE_SCRIPT"
    exit 1
fi

# Optional: Get Bicep deployment credentials
if [[ "$GET_BICEP_CREDS" = true ]]; then
    echo "======================================"
    echo "RETRIEVING BICEP DEPLOYMENT CREDENTIALS"
    echo "======================================"
    BICEP_CREDS_SCRIPT="$SCRIPT_DIR/utils/shells/get_bicep_creds.sh"
    
    if [[ -f "$BICEP_CREDS_SCRIPT" ]]; then
        echo "Getting Bicep deployment credentials..."
        bash "$BICEP_CREDS_SCRIPT" "$SUBSCRIPTION_ID" "$RESOURCE_GROUP"
        
        if [[ $? -ne 0 ]]; then
            echo "Warning: Failed to retrieve Bicep credentials."
        else
            echo "Bicep credentials retrieved successfully."
        fi
    else
        echo "Warning: Bicep credentials script not found at $BICEP_CREDS_SCRIPT"
    fi
fi

echo "======================================"
echo "CONFIGURATION COMPLETE"
echo "======================================"
echo "Subscription ID: $SUBSCRIPTION_ID"
echo "Resource Group: $RESOURCE_GROUP"
echo "Storage Account: $STORAGE_ACCOUNT"
echo "CosmosDB Account: $COSMOS_ACCOUNT"
echo "Principal ID: $PRINCIPAL_ID"
if [[ "$GET_BICEP_CREDS" = true ]]; then
    echo "Bicep credentials retrieved for subscription: $SUBSCRIPTION_ID"
fi
echo ""
echo "All resources are now configured with public network access and proper role assignments."
echo "For security in production environments, consider restricting network access after development."