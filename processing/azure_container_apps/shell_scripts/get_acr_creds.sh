#!/usr/bin/env bash

# Usage: ./get_acr_credentials.sh <SUBSCRIPTION_ID> <RESOURCE_GROUP_NAME>
# Example: ./get_acr_credentials.sh 00000000-0000-0000-0000-000000000000 MyResourceGroup

SUBSCRIPTION_ID="$1"
RESOURCE_GROUP_NAME="$2"

if [ -z "$SUBSCRIPTION_ID" ] || [ -z "$RESOURCE_GROUP_NAME" ]; then
  echo "Usage: $0 <subscription-id> <resource-group-name>" >&2
  exit 1
fi

# Set the Azure subscription
echo "[INFO] Setting subscription to $SUBSCRIPTION_ID..." >&2
az account set --subscription "$SUBSCRIPTION_ID"

# 1) Fetch ACR names (one per line), removing '\r' for Windows shells
ACR_NAMES_RAW=$(az acr list \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP_NAME" \
  --query '[].name' \
  -o tsv | tr -d '\r')

echo "[DEBUG] ACR_NAMES_RAW: $ACR_NAMES_RAW" >&2

# 2) Use mapfile/readarray to split multiline string into an array
#    This ensures each line is an element in the array.
#    '-t' strips newlines.
mapfile -t ACR_ARRAY <<< "$ACR_NAMES_RAW"

# If we have zero elements, print [] and exit
if [ ${#ACR_ARRAY[@]} -eq 0 ]; then
  echo "[]"
  exit 0
fi

echo "[DEBUG] ACR_ARRAY content: ${ACR_ARRAY[@]}" >&2

acr_list=()

# 3) Loop over each ACR in the array
for ACR_NAME in "${ACR_ARRAY[@]}"; do
  echo "[INFO] Processing ACR: $ACR_NAME" >&2

  # Attempt to enable admin user
  az acr update -n "$ACR_NAME" \
    --subscription "$SUBSCRIPTION_ID" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --admin-enabled true \
    1>/dev/null 2>/dev/null

  if [ $? -ne 0 ]; then
    echo "[WARN] Skipping '$ACR_NAME' because 'az acr update' failed." >&2
    continue
  fi

  # Grab the login server
  ACR_LOGIN_SERVER=$(az acr show \
    --name "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --subscription "$SUBSCRIPTION_ID" \
    --query "loginServer" -o tsv 2>/dev/null | tr -d '[:space:]')

  if [ -z "$ACR_LOGIN_SERVER" ]; then
    echo "[WARN] Skipping '$ACR_NAME' because we could not retrieve loginServer." >&2
    continue
  fi

  # Grab the admin username
  ACR_USER=$(az acr credential show \
    --name "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --subscription "$SUBSCRIPTION_ID" \
    --query "username" -o tsv 2>/dev/null | tr -d '[:space:]')

  if [ -z "$ACR_USER" ]; then
    echo "[WARN] Skipping '$ACR_NAME' because we could not retrieve username." >&2
    continue
  fi

  # Grab the first password
  ACR_PASSWORD=$(az acr credential show \
    --name "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --subscription "$SUBSCRIPTION_ID" \
    --query "passwords[0].value" -o tsv 2>/dev/null | tr -d '[:space:]')

  if [ -z "$ACR_PASSWORD" ]; then
    echo "[WARN] Skipping '$ACR_NAME' because we could not retrieve a password." >&2
    continue
  fi

  # Build a JSON object for this ACR
  acr_info=$(jq -n \
    --arg name "$ACR_NAME" \
    --arg server "$ACR_LOGIN_SERVER" \
    --arg username "$ACR_USER" \
    --arg password "$ACR_PASSWORD" \
    '{name: $name, server: $server, username: $username, password: $password}')

  # Collect it in our array
  acr_list+=("$acr_info")
done

# Print as a JSON array
printf '%s\n' "${acr_list[@]}" | jq -s '.'
