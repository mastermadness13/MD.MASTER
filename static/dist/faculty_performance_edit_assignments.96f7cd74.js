const BOOT=window.FACULTY_EDIT_ASSIGNMENTS_BOOT||{},TASK_HOURS=BOOT.taskHours||{};function esc(e){return String(e==null?"":e).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;")}function autoFillHours(e){const t=e.closest(".assignment-row").querySelector('input[name="auto_hours[]"]'),n=e.value;TASK_HOURS[n]!==void 0?t.value=TASK_HOURS[n]:t.value=""}function addAssignmentRow(){const e=document.getElementById("assignments-container"),o=BOOT.taskTypes||[];let t='<option value="">\u2014 \u0627\u062E\u062A\u0631 \u2014</option>';o.forEach(a=>{t+='<option value="'+esc(a.name)+'">'+esc(a.name)+"</option>"});const n=`
    <div class="assignment-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">
      <div class="flex-1 min-w-[200px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0627\u0644\u0645\u0647\u0645\u0629 \u0627\u0644\u0625\u062F\u0627\u0631\u064A\u0629</label>
        <select name="task_name[]" required onchange="autoFillHours(this)" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">${t}</select>
      </div>
      <div class="w-20">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0627\u0644\u0633\u0627\u0639\u0627\u062A (\u062A\u0644\u0642\u0627\u0626\u064A)</label>
        <input type="number" name="auto_hours[]" min="0" value="" readonly class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm bg-gray-50 text-on-surface-variant outline-none">
      </div>
      <div class="w-20">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0633\u0627\u0639\u0627\u062A \u064A\u062F\u0648\u064A\u0629</label>
        <input type="number" name="manual_hours[]" min="1" max="24" value="0" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u062A\u0627\u0631\u064A\u062E \u0627\u0644\u062A\u0643\u0644\u064A\u0641</label>
        <input type="date" name="assignment_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0645\u0646 \u062A\u0627\u0631\u064A\u062E</label>
        <input type="date" name="start_date[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0625\u0644\u0649 \u062A\u0627\u0631\u064A\u062E</label>
        <input type="date" name="end_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[120px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0645\u0644\u0627\u062D\u0638\u0627\u062A</label>
        <input type="text" name="notes[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none" placeholder="\u0627\u062E\u062A\u064A\u0627\u0631\u064A">
      </div>
      <button type="button" onclick="this.closest('.assignment-row').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">
        <span class="material-symbols-outlined text-lg">delete</span>
      </button>
    </div>`;e.insertAdjacentHTML("beforeend",n)}
