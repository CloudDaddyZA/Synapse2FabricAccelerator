"""Azure management-plane SDK client factory."""
from __future__ import annotations

import logging

from azure.core.credentials import TokenCredential
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.synapse import SynapseManagementClient

logger = logging.getLogger("azure_clients")


class AzureClients:
    """Lazily-created management clients keyed by subscription."""

    def __init__(self, credential: TokenCredential):
        self.credential = credential
        self._synapse: dict[str, SynapseManagementClient] = {}
        self._resource: dict[str, ResourceManagementClient] = {}

    def subscriptions(self) -> SubscriptionClient:
        return SubscriptionClient(self.credential)

    def resource_graph(self) -> ResourceGraphClient:
        return ResourceGraphClient(self.credential)

    def synapse(self, subscription_id: str) -> SynapseManagementClient:
        if subscription_id not in self._synapse:
            self._synapse[subscription_id] = SynapseManagementClient(
                self.credential, subscription_id
            )
        return self._synapse[subscription_id]

    def resource(self, subscription_id: str) -> ResourceManagementClient:
        if subscription_id not in self._resource:
            self._resource[subscription_id] = ResourceManagementClient(
                self.credential, subscription_id
            )
        return self._resource[subscription_id]
