
const BOOT = window.FACULTY_EDIT_ASSIGNMENTS_BOOT || {};
const TASK_HOURS = BOOT.taskHours || {};

function autoFillHours(selectEl) {
  const row = selectEl.closest('.assignment-row');
  const autoInput = row.querySelector('input[name="auto_hours[]"]');
  const taskName = selectEl.value;
  if (TASK_HOURS[taskName] !== undefined) {
    autoInput.value = TASK_HOURS[taskName];
  } else {
    autoInput.value = '';
  }
}

function addAssignmentRow() {
  const container = document.getElementById('assignments-container');
  const types = BOOT.taskTypes || [];
  let taskOptions = '<option value="">— اختر —</option>';
  types.forEach(t => { taskOptions += '<option value="' + t.name + '">' + t.name + '</option>'; });

  const html = `
    <div class="assignment-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">
      <div class="flex-1 min-w-[200px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">المهمة الإدارية</label>
        <select name="task_name[]" required onchange="autoFillHours(this)" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">${taskOptions}</select>
      </div>
      <div class="w-20">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">الساعات (تلقائي)</label>
        <input type="number" name="auto_hours[]" min="0" value="" readonly class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm bg-gray-50 text-on-surface-variant outline-none">
      </div>
      <div class="w-20">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">ساعات يدوية</label>
        <input type="number" name="manual_hours[]" min="1" max="24" value="0" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">تاريخ التكليف</label>
        <input type="date" name="assignment_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">من تاريخ</label>
        <input type="date" name="start_date[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">إلى تاريخ</label>
        <input type="date" name="end_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[120px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">ملاحظات</label>
        <input type="text" name="notes[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none" placeholder="اختياري">
      </div>
      <button type="button" onclick="this.closest('.assignment-row').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">
        <span class="material-symbols-outlined text-lg">delete</span>
      </button>
    </div>`;
  container.insertAdjacentHTML('beforeend', html);
}
