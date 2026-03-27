// code/components/TodoList.js
import { createTodoItemEl } from './TodoItem.js';

export function renderTodoList(container, todos, { onToggle, onDelete }) {
  if (!container) throw new Error('container is required');

  container.innerHTML = '';

  if (!Array.isArray(todos) || todos.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'todo-list__empty';
    empty.textContent = '할일이 없습니다.';
    container.appendChild(empty);
    return;
  }

  const fragment = document.createDocumentFragment();

  todos.forEach((todo) => {
    const item = createTodoItemEl(todo, { onToggle, onDelete });
    fragment.appendChild(item);
  });

  container.appendChild(fragment);
}