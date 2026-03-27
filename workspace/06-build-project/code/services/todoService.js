// code/services/todoService.js
import { createTodo, TODO_STATUS } from '../models/todo.js';
import { storageAdapter } from '../storage/localStorageAdapter.js';
import { validateTitle } from '../utils/validator.js';

export const todoService = {
  getAll() {
    return storageAdapter.load();
  },

  add(title) {
    const trimmed = title?.trim() ?? '';
    validateTitle(trimmed);
    const todo = createTodo(trimmed);
    const todos = storageAdapter.load();
    todos.push(todo);
    storageAdapter.save(todos);
    return todo;
  },

  complete(id) {
    const todos = storageAdapter.load();
    const target = todos.find(t => t.id === id);
    if (!target) throw new Error(`Todo not found: ${id}`);
    target.status = TODO_STATUS.DONE;
    storageAdapter.save(todos);
    return target;
  },

  remove(id) {
    const todos = storageAdapter.load();
    const filtered = todos.filter(t => t.id !== id);
    if (filtered.length === todos.length) throw new Error(`Todo not found: ${id}`);
    storageAdapter.save(filtered);
  },
};