import { api, apiBase, getActiveOrg, getToken } from "./api";

export type FavoriteItem = {id:string;target_type:"artist"|"venue";target_id:string};

/** Share only simultaneous reads, scoped to the API, session and organization. */
export function createFavoriteReader(load:()=>Promise<FavoriteItem[]>, scope:()=>string) {
  const pending = new Map<string,Promise<FavoriteItem[]>>();
  return () => {
    const key = scope();
    const existing = pending.get(key);
    if (existing) return existing;
    const request = load().finally(() => {
      if (pending.get(key) === request) pending.delete(key);
    });
    pending.set(key, request);
    return request;
  };
}

export const readFavorites = createFavoriteReader(
  async () => (await api<{items:FavoriteItem[]}>("/favorites")).items || [],
  () => JSON.stringify([apiBase(),getToken(),getActiveOrg()]),
);
