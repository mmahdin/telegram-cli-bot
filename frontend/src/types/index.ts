export type ChatType = 'private' | 'bot' | 'group';

export interface Dialog {
  id: number;
  name: string;
  username: string;
  phone: string;
  is_bot: boolean;
  is_group: boolean;
  chat_type: ChatType;
  is_important?: boolean;
  last_message: string;
  last_message_time: string | null;
  unread_count: number;
  avatar: string | null;
}

export interface MediaInfo {
  type: 'photo' | 'video' | 'audio' | 'voice' | 'document';
  filename?: string;
  mime?: string;
  size?: number;
  is_voice?: boolean;
  data: string | null;
  download_only?: boolean;
  download_url?: string | null;
}

export interface Message {
  id: number;
  event_type?: string;
  chat_id: number;
  sender_id: number | null;
  sender_name?: string | null;
  sender_username?: string | null;
  sender_avatar?: string | null;
  chat_type?: ChatType;
  is_outgoing: boolean;
  text: string;
  date: string | null;
  media: MediaInfo | null;
  reply_to_msg_id: number | null;
  edit_date: string | null;
}

export interface Me {
  id: number;
  name: string;
  username: string;
  phone: string;
  avatar: string | null;
}

export interface AuthStatus {
  connected: boolean;
  connecting: boolean;
  has_session: boolean;
  last_error: string | null;
  stealth_read?: boolean;
  stealth_presence?: boolean;
  stealth_disable_live_updates?: boolean;
  stealth_offline_refresh_seconds?: number;
  me: Me | null;
}
