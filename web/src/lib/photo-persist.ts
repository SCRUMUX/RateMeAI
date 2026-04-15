const DB_NAME = 'ailook_photo';
const STORE = 'pending';
const KEY = 'oauth_photo';
const META_KEY = 'ailook_oauth_ctx';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function savePhotoBeforeOAuth(
  file: File,
  ctx: { mode: string; style: string; scenarioSlug?: string; returnPath?: string },
): Promise<void> {
  try {
    const buf = await file.arrayBuffer();
    const db = await openDB();
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(
      { buffer: buf, name: file.name, type: file.type },
      KEY,
    );
    await new Promise<void>((res, rej) => {
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
    db.close();
    sessionStorage.setItem(META_KEY, JSON.stringify(ctx));
  } catch {
    // Best-effort — don't block OAuth redirect
  }
}

export interface RestoredPhoto {
  file: File;
  mode: string;
  style: string;
  scenarioSlug?: string;
  returnPath?: string;
}

export async function restorePhotoAfterOAuth(): Promise<RestoredPhoto | null> {
  try {
    const raw = sessionStorage.getItem(META_KEY);
    if (!raw) return null;

    const db = await openDB();
    const tx = db.transaction(STORE, 'readonly');
    const getReq = tx.objectStore(STORE).get(KEY);
    const record = await new Promise<any>((res, rej) => {
      getReq.onsuccess = () => res(getReq.result);
      getReq.onerror = () => rej(getReq.error);
    });
    db.close();

    if (!record) return null;

    const file = new File([record.buffer], record.name, { type: record.type });
    const ctx = JSON.parse(raw);
    return {
      file,
      mode: ctx.mode || '',
      style: ctx.style || '',
      scenarioSlug: ctx.scenarioSlug || undefined,
      returnPath: ctx.returnPath || undefined,
    };
  } catch {
    return null;
  }
}

export async function clearPersistedPhoto(): Promise<void> {
  try {
    sessionStorage.removeItem(META_KEY);
    const db = await openDB();
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(KEY);
    await new Promise<void>((res) => { tx.oncomplete = () => res(); });
    db.close();
  } catch {
    // ignore
  }
}
