// code/models/todo.js

export const TODO_STATUS = Object.freeze({
  ACTIVE: 'active',
  DONE: 'done',
});

/**
 * @param {string} title
 * @returns {{ id: string, title: string, status: string, createdAt: string }}
 */
export function createTodo(title) {
  if (typeof title !== 'string' || title.trim() === '') {
    throw new Error('title은 비어있을 수 없습니다.');
  }

  return Object.freeze({
    id: crypto.randomUUID(),
    title: title.trim(),
    status: TODO_STATUS.ACTIVE,
    createdAt: new Date().toISOString(),
  });
}