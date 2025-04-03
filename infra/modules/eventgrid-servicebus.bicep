@description('Event Grid System Topic ID from Storage account')
param eventGridSystemTopicId string

@description('Service Bus Queue ID that will receive the events')
param serviceBusQueueId string

@description('User Assigned Identity Principal ID for authentication between Event Grid and Service Bus')
param userAssignedIdentityId string

@description('Name for the Event Grid subscription')
param eventGridSubscriptionName string = 'storage-to-servicebus'

@description('Blob event types to filter. Empty means all events.')
param blobEventTypes array = [
  'Microsoft.Storage.BlobCreated'
]

@description('Optional subject filters for blob events')
param subjectFilters object = {
  subjectBeginsWith: ''
  subjectEndsWith: ''
}

@description('Event Time to Live in minutes')
param eventTimeToLiveInMinutes int = 1440 // 24 hours

@description('Maximum retries for event delivery')
param maxDeliveryAttempts int = 30

@description('Namespace ID for the Service Bus Queue')
param namespaceId string 


// Event Grid Subscription Resource: mmstpd-blob-events/blob-to-servicebus
resource eventGridSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2025-02-15' = {
  name:'${split(eventGridSystemTopicId, '/')[8]}/${eventGridSubscriptionName}'
  properties: {
    destination: {
      properties: {
        resourceId: serviceBusQueueId
      }
      endpointType: 'ServiceBusQueue'
    }
    filter: {
      includedEventTypes: empty(blobEventTypes) ? null : blobEventTypes
      subjectBeginsWith: empty(subjectFilters.subjectBeginsWith) ? null : subjectFilters.subjectBeginsWith
      subjectEndsWith: empty(subjectFilters.subjectEndsWith) ? null : subjectFilters.subjectEndsWith
      enableAdvancedFilteringOnArrays: true
      isSubjectCaseSensitive: false
    }
    eventDeliverySchema: 'EventGridSchema'
    labels: []
    retryPolicy: {
      maxDeliveryAttempts: maxDeliveryAttempts
      eventTimeToLiveInMinutes: eventTimeToLiveInMinutes
    }
  }
}

// Output the Event Grid Subscription resource ID for reference
output eventGridSubscriptionId string = eventGridSubscription.id
output eventGridSubscriptionName string = eventGridSubscriptionName
