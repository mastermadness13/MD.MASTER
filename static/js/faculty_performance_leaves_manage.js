
function addLeaveRow() {
  const container = document.getElementById('leaves-container');
  const BOOT = window.FACULTY_LEAVES_MANAGE_BOOT || {};
const types = BOOT.leaveTypes || [];
  let ltOptions = '<option value="">— اختر —</option>';
  types.forEach(t => { ltOptions += '<option value="' + t + '">' + t + '</option>'; });

  const html = `
    <div class="leave-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">
      <div class="flex-1 min-w-[160px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">نوع القرار</label>
        <select name="leave_type[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">${ltOptions}</select>
      </div>
      <div class="flex-1 min-w-[130px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">رقم القرار</label>
        <input type="text" name="decision_number[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[130px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">جهة الإصدار</label>
        <input type="text" name="decision_authority[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">تاريخ القرار</label>
        <input type="date" name="decision_date[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">من تاريخ</label>
        <input type="date" name="start_date[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">إلى تاريخ</label>
        <input type="date" name="end_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-28">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">الساعات</label>
        <input type="number" name="hours[]" value="0" min="1" max="24" step="1" inputmode="numeric" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[100px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">ملاحظات</label>
        <input type="text" name="notes[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none" placeholder="اختياري">
      </div>
      <button type="button" onclick="this.closest('.leave-row').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">
        <span class="material-symbols-outlined text-lg">delete</span>
      </button>
    </div>`;
  container.insertAdjacentHTML('beforeend', html);
}
