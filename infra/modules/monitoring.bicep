@description('Location for the resource')
param location string

@description('Whether to create a new Log Analytics workspace for monitoring.')
param createLogAnalytics bool

@minLength(4)
@maxLength(63)
@description('Name of the Log Analytics workspace')
param logAnalyticsName string

@description('Name of the Application Insights resource to create.')
param appInsightsName string

@description('Tags to apply to resources')
param tags object

@description('User Assigned Identity Principal ID for access control')
param userAssignedIdentityPrincipalId string

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = if (createLogAnalytics) {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (createLogAnalytics) {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: createLogAnalytics ? logAnalytics.id : ''
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}



// Assign the User Assigned Identity Contributor role
resource storageAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(appInsights.id, userAssignedIdentityPrincipalId, 'Monitoring Contributor')
  scope: appInsights
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '749f88d5-cbae-40b8-bcfc-e573ddc772fa') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}



output logAnalyticsId string = createLogAnalytics ? logAnalytics.id : ''
output appInsightsName string = createLogAnalytics ? appInsights.name : 'No App Insights created'
output appInsightsInstrumentationKey string = createLogAnalytics ? appInsights.properties.InstrumentationKey : ''
output appInsightsConnectionString string = createLogAnalytics ? appInsights.properties.ConnectionString : ''
