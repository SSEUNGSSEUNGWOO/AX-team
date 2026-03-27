import { todoService } from './services/todoService.js';
import { renderTodoList } from './components/TodoList.js';
import { validateTitle } from './utils/validator.js';
import { migrateStorage } from './utils/migrationUtil.js';

function init() {
  migrateStorage();

  const form = document.getElementById('todo-form');
  const input = document.getElementById('todo-input');
  const listContainer = document.getElementById('todo-list');

  function refresh() {
    const todos = todoService.getAll();
    renderTodoList(listContainer, todos, {
      onToggle: (id) => {
        todoService.toggle(id);
        refresh();
      },
      onDelete: (id) => {
        todoService.remove(id);
        refresh();
      },
    });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const title = input.value.trim();
    const error = validateTitle(title);
    if (error) return;
    todoService.add(title);
    input.value = '';
    refresh();
  });

  refresh();
}

init();