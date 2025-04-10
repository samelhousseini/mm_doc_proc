#!/bin/bash

# https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access?tabs=custom-definition%2Ccsharp&pivots=azure-interface-cli

# SAMPLE USAGE:
# bash custom-role.sh --resource-group "<RG>" --account-name "<COSMOS_RESOURCE>" --principal-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" --role-name "Azure Cosmos DB for NoSQL Data Plane Owner Custom Role" --auto-assign

# Set default values
RESOURCE_GROUP=""
ACCOUNT_NAME=""
ROLE_DEFINITION_FILE="role-definition.json"
ROLE_DEFINITION_ID=""
PRINCIPAL_ID=""
SUBSCRIPTION_ID=""
COSMOS_SCOPE=""
ROLE_NAME=""
AUTO_ASSIGN=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --resource-group|-g)
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --account-name|-a)
      ACCOUNT_NAME="$2"
      shift 2
      ;;
    --role-definition-file|-f)
      ROLE_DEFINITION_FILE="$2"
      shift 2
      ;;
    --role-definition-id|-r)
      ROLE_DEFINITION_ID="$2"
      shift 2
      ;;
    --principal-id|-p)
      PRINCIPAL_ID="$2"
      shift 2
      ;;
    --subscription-id|-s)
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --role-name|-n)
      ROLE_NAME="$2"
      shift 2
      ;;
    --auto-assign|-aa)
      AUTO_ASSIGN=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --resource-group, -g     Resource group name"
      echo "  --account-name, -a       Cosmos DB account name"
      echo "  --role-definition-file, -f  Path to role definition JSON file (default: role-definition.json)"
      echo "  --role-definition-id, -r  Role definition ID (required for role assignment)"
      echo "  --principal-id, -p       Principal ID for role assignment"
      echo "  --subscription-id, -s    Subscription ID"
      echo "  --role-name, -n          Role name to look for in the list of role definitions"
      echo "  --auto-assign, -aa       Automatically assign the role after creating the definition"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done

# Check required parameters
if [[ -z "$RESOURCE_GROUP" ]]; then
  echo "Error: Resource group name is required (--resource-group)"
  exit 1
fi

if [[ -z "$ACCOUNT_NAME" ]]; then
  echo "Error: Cosmos DB account name is required (--account-name)"
  exit 1
fi

# Create a new role definition
echo "Creating new role definition from $ROLE_DEFINITION_FILE..."
az cosmosdb sql role definition create --resource-group "$RESOURCE_GROUP" --account-name "$ACCOUNT_NAME" --body "@$ROLE_DEFINITION_FILE"

# List role definitions
echo "Listing role definitions..."
ROLE_DEFINITIONS=$(az cosmosdb sql role definition list --resource-group "$RESOURCE_GROUP" --account-name "$ACCOUNT_NAME")
echo "$ROLE_DEFINITIONS"

# Extract the role definition ID based on role name if specified
if [[ -n "$ROLE_NAME" && -z "$ROLE_DEFINITION_ID" ]]; then
  echo "Searching for role definition with name: $ROLE_NAME"
  ROLE_DEFINITION_ID=$(echo "$ROLE_DEFINITIONS" | jq -r --arg NAME "$ROLE_NAME" '.[] | select(.roleName == $NAME) | .id')
  
  if [[ -n "$ROLE_DEFINITION_ID" ]]; then
    echo "Found role definition ID for role '$ROLE_NAME': $ROLE_DEFINITION_ID"
  else
    echo "Warning: Could not find a role definition with name '$ROLE_NAME'"
    
    # If we need to auto-assign and don't have the role ID, let's try to use the latest created role
    if [[ "$AUTO_ASSIGN" == true ]]; then
      echo "Attempting to use the most recently created role definition..."
      ROLE_DEFINITION_ID=$(echo "$ROLE_DEFINITIONS" | jq -r '.[0].id')
      if [[ -n "$ROLE_DEFINITION_ID" ]]; then
        echo "Using role definition ID: $ROLE_DEFINITION_ID"
      fi
    fi
  fi
fi

# Get the Cosmos DB account ID
echo "Getting Cosmos DB account ID..."
COSMOS_ID=$(az cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$ACCOUNT_NAME" --query "{id:id}" -o tsv)
echo "Cosmos DB ID: $COSMOS_ID"

# Create a role assignment if either:
# 1. We have explicit ROLE_DEFINITION_ID and PRINCIPAL_ID
# 2. AUTO_ASSIGN is true, we have PRINCIPAL_ID, and we managed to get a ROLE_DEFINITION_ID
if [[ (! -z "$ROLE_DEFINITION_ID" && ! -z "$PRINCIPAL_ID") || ("$AUTO_ASSIGN" == true && ! -z "$PRINCIPAL_ID" && ! -z "$ROLE_DEFINITION_ID") ]]; then
  # Use provided scope or default to account ID
  if [[ -z "$COSMOS_SCOPE" ]]; then
    COSMOS_SCOPE="$COSMOS_ID"
  fi
  
  echo "Creating role assignment..."
  az cosmosdb sql role assignment create \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$ACCOUNT_NAME" \
    --role-definition-id "$ROLE_DEFINITION_ID" \
    --principal-id "$PRINCIPAL_ID" \
    --scope "$COSMOS_SCOPE"
  
  echo "Role assignment created successfully."
else
  if [[ -z "$PRINCIPAL_ID" ]]; then
    echo "Skipping role assignment creation. To create an assignment, provide --principal-id parameter."
  elif [[ -z "$ROLE_DEFINITION_ID" ]]; then
    echo "Skipping role assignment creation. No role definition ID found or specified."
    echo "You can provide a specific role definition ID with --role-definition-id"
    echo "Or specify a role name to search for with --role-name"
  else
    echo "Skipping role assignment creation. Missing required parameters."
  fi
  
  # Display a summary of available roles to help the user
  echo -e "\nAvailable role definitions:"
  echo "$ROLE_DEFINITIONS" | jq -r '.[] | "ID: \(.id)\nName: \(.roleName)\n"'
fi



