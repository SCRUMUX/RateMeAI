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
  provider: 'yandex' | 'vk-id' | 'google',
  photoCtx?: {
    file: File;
    mode: string;
    style: string;
    scenarioSlug?: string;
    returnPath?: string;
  },
  linkCode?: string,
  returnPath?: string,
) {
  const deviceId = getDeviceId();
  if (photoCtx?.file) {
    await savePhotoBeforeOAuth(photoCtx.file, {
      mode: photoCtx.mode,
      style: photoCtx.style,
      scenarioSlug: photoCtx.scenarioSlug,
      returnPath: photoCtx.returnPath,
    });
  }
  // ``returnPath`` is sent to the backend so it can survive the OAuth
  // round-trip via Redis ``state``. ``photoCtx?.returnPath`` is the
  // legacy IndexedDB-only path and is only set when there is a photo;
  // we prefer the explicit argument for the call to oauthInit so visa
  // landings (no photo yet) still get a return path on the server.
  const effectiveReturnPath = returnPath ?? photoCtx?.returnPath;
  const res = await oauthInit(provider, deviceId, linkCode, effectiveReturnPath);
  window.location.href = res.authorize_url;
}

export function logout() {
  setToken(null);
}
