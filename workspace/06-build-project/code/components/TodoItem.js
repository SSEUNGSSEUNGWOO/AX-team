// code/components/TodoItem.js
import { TODO_STATUS } from '../models/todo.js';

export function createTodoItemEl(todo, { onToggle, onDelete }) {
  const li = document.createElement('li');
  li.dataset.id = todo.id;
  li.className = `todo-item ${todo.status === TODO_STATUS.DONE ? 'done' : ''}`;

  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = todo.status === TODO_STATUS.DONE;
  checkbox.addEventListener('change', () => onToggle(todo.id));

  const span = document.createElement('span');
  span.className = 'todo-title';
  span.textContent = todo.title;

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'btn-delete';
  deleteBtn.textContent = '삭제';
  deleteBtn.addEventListener('click', () => onDelete(todo.id));

  li.append(checkbox, span, deleteBtn);
  return li;
}