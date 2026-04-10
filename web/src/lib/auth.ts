import { authWeb, setToken as apiSetToken, getToken, oauthInit, type ChannelAuthResponse } from './api';
import { savePhotoBeforeOAuth } from './photo-persist';

const DEVICE_ID_KEY = 'ailook_device_id';
const TOKEN_KEY = 'ailook_session_token';

export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export function setToken(token: string | null) {
  apiSetToken(token);
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function restoreToken(): string | null {
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) apiSetToken(t);
  return t;
}

export async function login(): Promise<ChannelAuthResponse> {
  const deviceId = getDeviceId();
  const res = await authWeb(deviceId);
  setToken(res.session_token);
  return res;
}

export async function startOAuth(
  provider: 'yandex' | 'vk-id',
  photoCtx?: { file: File; mode: string; style: string },
  linkCode?: string,
) {
  const deviceId = getDeviceId();
  if (photoCtx?.file) {
    await savePhotoBeforeOAuth(photoCtx.file, {
      mode: photoCtx.mode,
      style: photoCtx.style,
    });
  }
  const res = await oauthInit(provider, deviceId, linkCode);
  window.location.href = res.authorize_url;
}

export function logout() {
  setToken(null);
}
