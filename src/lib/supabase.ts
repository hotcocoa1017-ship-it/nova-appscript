/**
 * NOVA Realtime & Supabase Client Manager
 * Handles resilient channel subscription, broadcast event dispatch, automatic reconnection,
 * client-server reconciliation, and online/offline network lifecycle.
 */

import { createClient, RealtimeChannel, SupabaseClient } from '@supabase/supabase-js';
import { RoomEntity } from './types';

export type RealtimeConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR';

let supabaseClient: SupabaseClient | null = null;
const activeChannels = new Map<string, RealtimeChannel>();

export function getSupabaseClient(supabaseUrl?: string, publishableKey?: string): SupabaseClient | null {
  if (supabaseClient) return supabaseClient;

  const url = supabaseUrl || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = publishableKey || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key || url.includes('placeholder')) {
    return null;
  }

  supabaseClient = createClient(url, key, {
    realtime: {
      params: {
        eventsPerSecond: 20
      }
    }
  });

  return supabaseClient;
}

export interface RealtimeSubscriptionOptions {
  site: string;
  onRoomUpdated: (updatedRoom: Partial<RoomEntity> & { roomNo: string }) => void;
  onConnectionChange?: (status: RealtimeConnectionStatus) => void;
  onReconcileNeeded?: () => void; // Triggered when reconnecting after drop or sleep
}

/**
 * Subscribes to the site-isolated broadcast channel (`nova:site:<site>:rooms`)
 * with robust auto-reconnection and reconciliation safeguards.
 */
export function subscribeToSiteRooms(
  client: SupabaseClient,
  options: RealtimeSubscriptionOptions
): RealtimeChannel {
  const { site, onRoomUpdated, onConnectionChange, onReconcileNeeded } = options;
  const topic = `nova:site:${site}:rooms`;

  // 1. Prevent duplicate subscriptions on same topic
  if (activeChannels.has(topic)) {
    const existing = activeChannels.get(topic)!;
    existing.unsubscribe();
    activeChannels.delete(topic);
  }

  onConnectionChange?.('CONNECTING');

  const channel = client.channel(topic, {
    config: {
      broadcast: { ack: false }
    }
  });

  // 2. Broadcast Listener: Apply incremental updates without full reload
  channel
    .on('broadcast', { event: '*' }, (payload) => {
      try {
        const record = payload.payload?.new || payload.payload?.record || payload.payload;
        if (record && record.room_no) {
          onRoomUpdated({
            roomNo: String(record.room_no),
            roomStatus: record.room_status,
            cleaningStatus: record.cleaning_status,
            version: Number(record.version || 1),
            cleaningStartedAt: record.cleaning_started_at,
            cleaningCompletedAt: record.cleaning_completed_at,
            updatedBy: record.updated_by,
            updatedAt: record.updated_at
          });
        }
      } catch (err) {
        console.error('[Realtime Broadcast Parse Error]:', err);
      }
    })
    .subscribe((status) => {
      if (status === 'SUBSCRIBED') {
        onConnectionChange?.('CONNECTED');
      } else if (status === 'CLOSED' || status === 'CHANNEL_ERROR') {
        onConnectionChange?.('DISCONNECTED');
        onReconcileNeeded?.();
      } else if (status === 'TIMED_OUT') {
        onConnectionChange?.('ERROR');
        onReconcileNeeded?.();
      }
    });

  // 3. Browser Online/Offline and Sleep/Wake Resiliency
  if (typeof window !== 'undefined') {
    const handleOnline = () => {
      onConnectionChange?.('CONNECTING');
      onReconcileNeeded?.();
    };

    const handleOffline = () => {
      onConnectionChange?.('DISCONNECTED');
    };

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        // App woke up from sleep or mobile background: reconcile latest state
        onReconcileNeeded?.();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    document.addEventListener('visibilitychange', handleVisibility);

    // Save cleanup references
    const originalUnsubscribe = channel.unsubscribe.bind(channel);
    channel.unsubscribe = async () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      document.removeEventListener('visibilitychange', handleVisibility);
      activeChannels.delete(topic);
      return originalUnsubscribe();
    };
  }

  activeChannels.set(topic, channel);
  return channel;
}
