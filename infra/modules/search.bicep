@description('Location for the resource')
param location string

@description('Whether to create a new Cognitive Search service')
param createSearch bool

@minLength(2)
@maxLength(60)
@description('Name for the Cognitive Search service to create')
param searchServiceName string

@description('If not creating new, supply existing search service admin key.')
@secure()
param existingSearchAdminKey string = ''

@description('If not creating new, supply existing search service endpoint')
param existingSearchResource string = ''

@description('SKU for Cognitive Search (e.g., basic, standard, etc.)')
@allowed([
  'basic'
  'standard'
  'standard2'
  'standard3'
])
param searchSku string

@description('Tags to apply to resources')
param tags object

@description('User Assigned Identity Principal ID for access control')
param userAssignedIdentityPrincipalId string


var debugInfo = {
  name: searchServiceName
  createNew: createSearch
  sku: searchSku
  endpoint: createSearch ? 'https://${searchServiceName}.search.windows.net' : 'https://${existingSearchResource}.search.windows.net'
}

resource searchService 'Microsoft.Search/searchServices@2022-09-01' = if (createSearch) {
  name: searchServiceName
  location: location
  tags: tags
  sku: {
    name: searchSku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
}

// Assign the User Assigned Identity Contributor
resource searchAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' =  if (createSearch) {
  name: guid(searchService.id, userAssignedIdentityPrincipalId, 'Contributor')
  scope: searchService
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}


resource existingSearchService 'Microsoft.Search/searchServices@2022-09-01' existing = if (!createSearch) {
  name: searchServiceName
}

// Assign the User Assigned Identity Contributor
resource existingSearchAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' =  if (!createSearch) {
  name: guid(existingSearchService.id, userAssignedIdentityPrincipalId, 'Contributor')
  scope: existingSearchService
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}




var searchEndpoint = createSearch ? 'https://${searchServiceName}.search.windows.net' :'https://${existingSearchResource}.search.windows.net'
var searchAdminKey = createSearch ? searchService.listAdminKeys().primaryKey : existingSearchAdminKey

// For existing search service, output the provided values
output searchServiceName string = createSearch ? searchService.name : existingSearchResource
output searchServiceEndpoint string = searchEndpoint
output searchServiceKey string = searchAdminKey
output debugLogs object = debugInfo
