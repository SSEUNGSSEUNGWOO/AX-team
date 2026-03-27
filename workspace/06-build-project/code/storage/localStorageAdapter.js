// code/storage/localStorageAdapter.js

const STORAGE_KEY = 'todo_app_v1';

export const storageAdapter = {
  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        console.warn('[storageAdapter] 잘못된 데이터 형식. 초기화합니다.');
        return [];
      }
      return parsed;
    } catch (e) {
      console.error('[storageAdapter] load 실패:', e);
      return [];
    }
  },

  save(todos) {
    if (!Array.isArray(todos)) {
      throw new TypeError('[storageAdapter] todos는 배열이어야 합니다.');
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
    } catch (e) {
      console.error('[storageAdapter] save 실패:', e);
      throw e;
    }
  },

  clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.error('[storageAdapter] clear 실패:', e);
      throw e;
    }
  },

  getKey() {
    return STORAGE_KEY;
  },
};