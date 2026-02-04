"""
Multi-Region AgentCore Memory Saver wrapper for disaster recovery.

This module provides a wrapper around AgentCoreMemorySaver that supports
dual-region writes for high availability and disaster recovery scenarios.

Read operations: Primary region only
Write operations: Both regions (success requires both to succeed)
"""

from typing import Any, AsyncIterator, Iterator, Optional, Sequence
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph_checkpoint_aws import AgentCoreMemorySaver


class MultiRegionAgentCoreMemorySaver(BaseCheckpointSaver):
    """
    A multi-region checkpoint saver that wraps AgentCoreMemorySaver.
    
    - Reads from primary region only
    - Writes to both primary and secondary regions
    - Write operations only return success when both regions succeed
    """

    def __init__(
        self,
        primary_region: str,
        secondary_region: str,
        primary_memory_id: str,
        secondary_memory_id: str,
    ):
        """
        Initialize the multi-region memory saver.

        Args:
            primary_region: Primary AWS region (e.g., 'us-west-2')
            secondary_region: Secondary AWS region for DR (e.g., 'eu-west-1')
            primary_memory_id: AgentCore Memory ID in the primary region
            secondary_memory_id: AgentCore Memory ID in the secondary region
        """
        super().__init__()
        self.primary_region = primary_region
        self.secondary_region = secondary_region
        self.primary_memory_id = primary_memory_id
        self.secondary_memory_id = secondary_memory_id
        
        self.primary_saver = AgentCoreMemorySaver(primary_memory_id, region_name=primary_region)
        self.secondary_saver = AgentCoreMemorySaver(secondary_memory_id, region_name=secondary_region)

    @property
    def config_specs(self):
        """Return config specs from primary saver."""
        return self.primary_saver.config_specs

    # -------------------------------------------------------------------------
    # Read Operations - Primary region only
    # -------------------------------------------------------------------------

    def get(self, config: RunnableConfig) -> Optional[Checkpoint]:
        """Fetch a checkpoint from primary region."""
        return self.primary_saver.get(config)

    async def aget(self, config: RunnableConfig) -> Optional[Checkpoint]:
        """Async fetch a checkpoint from primary region."""
        return await self.primary_saver.aget(config)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple from primary region."""
        return self.primary_saver.get_tuple(config)

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Async get a checkpoint tuple from primary region."""
        return await self.primary_saver.aget_tuple(config)

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from primary region."""
        yield from self.primary_saver.list(config, filter=filter, before=before, limit=limit)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Async list checkpoints from primary region."""
        async for checkpoint in self.primary_saver.alist(
            config, filter=filter, before=before, limit=limit
        ):
            yield checkpoint

    # -------------------------------------------------------------------------
    # Write Operations - Both regions (success requires both)
    # -------------------------------------------------------------------------

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Save a checkpoint to both regions.
        
        Returns success only when both regions succeed.
        Raises exception if either region fails.
        """
        # Write to primary first
        result = self.primary_saver.put(config, checkpoint, metadata, new_versions)
        
        # Write to secondary - if this fails, we have inconsistency
        # In production, you may want to implement compensation/rollback logic
        self.secondary_saver.put(config, checkpoint, metadata, new_versions)
        
        return result

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Async save a checkpoint to both regions.
        
        Returns success only when both regions succeed.
        """
        # Write to primary first
        result = await self.primary_saver.aput(config, checkpoint, metadata, new_versions)
        
        # Write to secondary
        await self.secondary_saver.aput(config, checkpoint, metadata, new_versions)
        
        return result

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        Store intermediate writes to both regions.
        
        Returns success only when both regions succeed.
        """
        self.primary_saver.put_writes(config, writes, task_id, task_path)
        self.secondary_saver.put_writes(config, writes, task_id, task_path)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        Async store intermediate writes to both regions.
        
        Returns success only when both regions succeed.
        """
        await self.primary_saver.aput_writes(config, writes, task_id, task_path)
        await self.secondary_saver.aput_writes(config, writes, task_id, task_path)

    def delete_thread(self, thread_id: str, actor_id: str = "") -> None:
        """
        Delete all checkpoints for a thread from both regions.
        
        Returns success only when both regions succeed.
        """
        self.primary_saver.delete_thread(thread_id, actor_id)
        self.secondary_saver.delete_thread(thread_id, actor_id)

    async def adelete_thread(self, thread_id: str, actor_id: str = "") -> None:
        """
        Async delete all checkpoints for a thread from both regions.
        
        Returns success only when both regions succeed.
        """
        await self.primary_saver.adelete_thread(thread_id, actor_id)
        await self.secondary_saver.adelete_thread(thread_id, actor_id)

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_next_version(self, current: Optional[str], channel: Optional[str] = None) -> str:
        """Generate the next version ID for a channel."""
        return self.primary_saver.get_next_version(current, channel)