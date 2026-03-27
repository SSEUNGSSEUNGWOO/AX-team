// code/utils/validator.js

export function validateTitle(title) {
  if (typeof title !== 'string') return { valid: false, error: '문자열이 아닙니다.' };
  if (title.trim() === '') return { valid: false, error: '빈 값은 입력할 수 없습니다.' };
  return { valid: true, error: null };
}