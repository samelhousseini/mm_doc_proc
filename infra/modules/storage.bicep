@description('Location for the resource')
param location string

@description('Whether to create a new storage account or use an existing one')
param createStorage bool = true

@description('Name of the storage account')
param storageAccountName string

@description('Blob container name for uploads.')
param uploadsContainerName string

@description('Blob container name for processed documents.')
param processedContainerName string

@description('Queue name for event-driven processing.')
param storageQueueName string

@description('Tags to apply to resources')
param tags object

@description('Log Analytics Workspace ID for diagnostics')
param logAnalyticsWorkspaceId string = ''

@description('User Assigned Identity Principal ID for access control')
param userAssignedIdentityPrincipalId string


var debugInfo = {
  name: storageAccountName
  uploadContainer: uploadsContainerName
  processedContainer: processedContainerName
  queue: storageQueueName
  diagnosticsEnabled: !empty(logAnalyticsWorkspaceId)
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2022-09-01' = if (createStorage) {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2022-09-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource uploadsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2022-09-01' = {
  name: uploadsContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource processedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2022-09-01' = {
  name: processedContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2022-09-01' = {
  name: 'default'
  parent: storageAccount
}

resource storageQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2022-09-01' = {
  name: storageQueueName
  parent: queueService
}

// Diagnostic Settings
resource storageDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'storageDiag'
  scope: storageAccount
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    storageAccountId: storageAccount.id
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// Event Grid System Topic for Blob Storage
resource blobEventGridSystemTopic 'Microsoft.EventGrid/systemTopics@2023-06-01-preview' = {
  name: '${storageAccountName}-blob-events'
  location: location
  tags: tags
  properties: {
    source: storageAccount.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}



// Assign the User Assigned Identity Contributor
resource storageAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(storageAccount.id, userAssignedIdentityPrincipalId, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}


// Assign the User Assigned Identity Contributor
resource storageQueueAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(storageAccount.id, userAssignedIdentityPrincipalId, 'Storage Queue Data Contributor role')
  scope: storageAccount
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}



var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'

output storageAccountName string = storageAccount.name
output storageAccountKey string = storageAccount.listKeys().keys[0].value
output storageConnectionString string = storageConnectionString
output uploadsContainerName string = uploadsContainerName
output processedContainerName string = processedContainerName
output queueName string = storageQueueName
output blobEventGridSystemTopicName string = blobEventGridSystemTopic.name
output blobEventGridSystemTopicId string = blobEventGridSystemTopic.id
output storageAccountId string = storageAccount.id
output storageBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output storageQueueEndpoint string = storageAccount.properties.primaryEndpoints.queue
output debugLogs object = debugInfo
