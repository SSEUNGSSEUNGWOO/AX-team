// code/utils/migrationUtil.js

const STORAGE_KEY = 'todos';
const CURRENT_SCHEMA_VERSION = 1;

function migrateV0ToV1(todos) {
  return todos.map(todo => ({
    id: todo.id ?? crypto.randomUUID(),
    title: todo.title ?? '',
    status: todo.status === 'completed' ? 'done' : (todo.status ?? 'active'),
    createdAt: todo.createdAt ?? new Date().toISOString(),
  }));
}

const migrations = [
  { version: 1, migrate: migrateV0ToV1 },
];

export function migrateStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    const parsed = JSON.parse(raw);
    const todos = Array.isArray(parsed) ? parsed : parsed?.todos ?? [];
    const storedVersion = typeof parsed?.schemaVersion === 'number' ? parsed.schemaVersion : 0;

    if (storedVersion >= CURRENT_SCHEMA_VERSION) return;

    let migrated = todos;
    for (const m of migrations) {
      if (storedVersion < m.version) {
        migrated = m.migrate(migrated);
      }
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated));
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}